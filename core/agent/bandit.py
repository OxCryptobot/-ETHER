"""Arm selection for real goals (batch 4, 2026-11-20). The honest gate is the only reward.

Why: the batch-2 learner is ``core.learning.BanditPolicy`` (epsilon-greedy with a
shrinkage prior, reward 0.75 pass / -0.9 fail). On the 1650 a real goal costs
~40-70 s (two guard runs + one or two 4B calls), so the loop gets a few hundred
graded pulls a day at best. With that little data the choice of explorer matters.
``scripts/bandit_sim.py`` compares the options with fixed seeds (docs/BANDITS.md).

``ETHER_BANDIT`` picks the selector for real goal kinds (fix_test / lint):

- ``thompson`` (default): Beta-Bernoulli Thompson sampling on reward 1 = honest
  pass with 0 regressions, 0 = anything else the model produced. Russo et al.,
  https://arxiv.org/abs/1707.02038 ; Chapelle & Li 2011.
- ``ucb``: UCB1 on the same 0/1 reward (Auer et al. 2002).
- ``egreedy``: the batch-2 path, byte-for-byte (BanditPolicy.select).
- ``linucb``: disjoint LinUCB over 7 goal features (Li et al. 2010). Data-hungry;
  kept for comparison, not recommended at 1650 pull rates.

Options: ``ETHER_BANDIT_GAMMA`` (default 1.0 = stationary; 0.98 = discounted, for
drift), ``ETHER_BANDIT_COST=1`` (pick by sampled pass rate per GPU-second; Xia et al.
2015), ``ETHER_BANDIT_ARMS`` (comma list; default REAL_ARMS), ``ETHER_BANDIT_FACTORED=1``
(style x context x retry factors, each with its own posterior).

State: ``<root>/memory/learning/bandit4_<kind>.json`` via core.spine.state_io
(single writer), capped at MAX_BUCKETS buckets and the allowed arm set.
Nothing here can pass a goal: it only decides what the 4B sees.
"""
from __future__ import annotations

import math
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ALGOS = ("thompson", "ucb", "egreedy", "linucb")
DEFAULT_ALGO = "thompson"
# multifile asks for "# file:" blocks and with_asserts for embedded asserts; a real-goal
# edit is one function (+ constants), so both only waste pulls. Override with ETHER_BANDIT_ARMS.
REAL_ARMS: Tuple[str, ...] = ("default", "minimal", "repair_heavy", "no_context", "repo_map_on")
FACTORS: Dict[str, Tuple[str, ...]] = {
    "style": ("plain", "minimal", "defensive"),
    "ctx": ("file", "none", "map"),
    "retry": ("1", "2"),
}
STYLE_ADDON = {
    "plain": "",
    "minimal": "Minimal code only. No comments. Shortest correct solution.",
    "defensive": "Be defensive; validate inputs; avoid edge-case crashes.",
}
MAX_BUCKETS = 24
PRIOR_SECS = 45.0
PRIOR_N = 2.0
PROMOTE_PROB = 0.9
MC_DRAWS = 256
FEATURES = ("bias", "assert", "via_sbfl", "via_frame", "lint", "retried", "tractability")


# ---------------------------------------------------------------- config

def algo(kind: str = "fix_test") -> str:
    """Selector for a goal kind. Legacy ladder and refactor (rule-based) stay on egreedy."""
    if kind not in ("fix_test", "lint"):
        return "egreedy"
    name = (os.getenv("ETHER_BANDIT") or DEFAULT_ALGO).strip().lower()
    return name if name in ALGOS else DEFAULT_ALGO


def gamma() -> float:
    try:
        g = float(os.getenv("ETHER_BANDIT_GAMMA", "1.0"))
    except ValueError:
        g = 1.0
    return min(1.0, max(0.5, g))


def cost_aware() -> bool:
    return os.getenv("ETHER_BANDIT_COST", "0") == "1"


def factored() -> bool:
    return os.getenv("ETHER_BANDIT_FACTORED", "0") == "1"


def arms() -> List[str]:
    from core.learning import STRATEGY_BEHAVIOUR

    raw = os.getenv("ETHER_BANDIT_ARMS", "")
    names = [a.strip() for a in raw.split(",") if a.strip()] if raw else list(REAL_ARMS)
    names = [a for a in names if a in STRATEGY_BEHAVIOUR]
    names = names or list(REAL_ARMS)
    try:
        from core.agent import exemplars

        if exemplars.arm_on() and exemplars.ARM not in names:
            names.append(exemplars.ARM)  # batch 7: ETHER_EXEMPLARS=1
    except Exception:
        pass
    return names


# ---------------------------------------------------------------- pure algorithms (shared with the simulator)

def _cell(stats: Dict[str, Dict[str, float]], arm: str) -> Dict[str, float]:
    return stats.setdefault(arm, {"s": 0.0, "f": 0.0, "n": 0, "secs": 0.0, "passes": 0})


def mean(cell: Dict[str, float]) -> float:
    return (1.0 + cell.get("s", 0.0)) / (2.0 + cell.get("s", 0.0) + cell.get("f", 0.0))


def mean_secs(stats: Dict[str, Dict[str, float]], arm: str) -> float:
    cell = stats.get(arm) or {}
    return (float(cell.get("secs", 0.0)) + PRIOR_SECS) / (int(cell.get("n", 0)) + 1)


def prior(stats: Dict[str, Dict[str, float]], kind: str = "pooled") -> Tuple[float, float]:
    """Beta prior. "pooled" (default): PRIOR_N pseudo-pulls at the bucket's pooled pass rate
    (empirical Bayes). Beta(1,1) is optimistic when true rates are ~0.1 and over-explores a
    5-arm, few-hundred-pull problem (bandit_sim: see docs/BANDITS.md)."""
    if kind == "uniform":
        return 1.0, 1.0
    s_tot = sum(float(c.get("s", 0.0)) for c in stats.values())
    f_tot = sum(float(c.get("f", 0.0)) for c in stats.values())
    m = (s_tot + 1.0) / (s_tot + f_tot + 2.0)
    return PRIOR_N * m, PRIOR_N * (1.0 - m)


def thompson_draws(stats: Dict[str, Dict[str, float]], arm_list: Sequence[str], rng: random.Random,
                   cost: bool = False, prior_kind: str = "pooled") -> Dict[str, float]:
    out = {}
    a0, b0 = prior(stats, prior_kind)
    for a in arm_list:
        c = stats.get(a) or {}
        theta = rng.betavariate(a0 + float(c.get("s", 0.0)), b0 + float(c.get("f", 0.0)))
        out[a] = theta / mean_secs(stats, a) if cost else theta
    return out


def ucb_scores(stats: Dict[str, Dict[str, float]], arm_list: Sequence[str], cost: bool = False) -> Dict[str, float]:
    """UCB1 on discounted counts (D-UCB when gamma < 1). Untried arms score +inf."""
    total = sum(float((stats.get(a) or {}).get("s", 0.0)) + float((stats.get(a) or {}).get("f", 0.0))
                for a in arm_list)
    out = {}
    for a in arm_list:
        c = stats.get(a) or {}
        n = float(c.get("s", 0.0)) + float(c.get("f", 0.0))
        if n <= 1e-9:
            out[a] = float("inf")
            continue
        val = float(c.get("s", 0.0)) / n + math.sqrt(2.0 * math.log(max(total, 1.0 + 1e-9)) / n)
        out[a] = val / mean_secs(stats, a) if cost else val
    return out


def select(name: str, stats: Dict[str, Dict[str, float]], arm_list: Sequence[str], rng: random.Random,
           cost: bool = False, prior_kind: str = "pooled") -> Tuple[str, str]:
    """(arm, reason) for thompson / ucb. Ties break by rng."""
    arm_list = list(arm_list)
    if name == "ucb":
        scores = ucb_scores(stats, arm_list, cost)
        reason = "cover" if any(math.isinf(v) for v in scores.values()) else "ucb"
    else:
        scores = thompson_draws(stats, arm_list, rng, cost, prior_kind)
        reason = "sample"
    best = max(scores.values())
    top = [a for a in arm_list if scores[a] >= best - 1e-12]
    return rng.choice(top), reason


def propensity(name: str, stats: Dict[str, Dict[str, float]], arm_list: Sequence[str], arm: str,
               seed: int = 0, draws: int = MC_DRAWS, cost: bool = False, prior_kind: str = "pooled") -> float:
    """P(select == arm). Exact for ucb ties, Monte Carlo for thompson. Logged for replay."""
    arm_list = list(arm_list)
    if name == "ucb":
        scores = ucb_scores(stats, arm_list, cost)
        best = max(scores.values())
        top = [a for a in arm_list if scores[a] >= best - 1e-12]
        return 1.0 / len(top) if arm in top else 1e-6
    rng = random.Random(seed)
    hits = 0
    for _ in range(draws):
        d = thompson_draws(stats, arm_list, rng, cost, prior_kind)
        if max(d, key=lambda a: (d[a], -arm_list.index(a))) == arm:
            hits += 1
    return max(1e-6, hits / float(draws))


def update(stats: Dict[str, Dict[str, float]], arm: str, reward01: int, secs: float = 0.0,
           g: float = 1.0) -> None:
    """Discount every arm in the bucket by g (dTS / D-UCB), then add the outcome."""
    if g < 1.0:
        for c in stats.values():
            c["s"] = float(c.get("s", 0.0)) * g
            c["f"] = float(c.get("f", 0.0)) * g
    c = _cell(stats, arm)
    if reward01:
        c["s"] = float(c["s"]) + 1.0
        c["passes"] = int(c.get("passes", 0)) + 1
    else:
        c["f"] = float(c["f"]) + 1.0
    c["n"] = int(c.get("n", 0)) + 1
    c["secs"] = float(c.get("secs", 0.0)) + max(0.0, float(secs or 0.0))


def prob_better(stats: Dict[str, Dict[str, float]], arm: str, incumbent: str, seed: int = 0,
                draws: int = 2000) -> float:
    """P(theta_arm > theta_incumbent) under the Beta posteriors."""
    rng = random.Random(seed)
    a, b = stats.get(arm) or {}, stats.get(incumbent) or {}
    wins = 0
    for _ in range(draws):
        if rng.betavariate(1 + a.get("s", 0.0), 1 + a.get("f", 0.0)) > rng.betavariate(1 + b.get("s", 0.0),
                                                                                       1 + b.get("f", 0.0)):
            wins += 1
    return wins / float(draws)


def entropy(stats: Dict[str, Dict[str, float]], arm_list: Sequence[str]) -> float:
    """Shannon entropy (bits) of the pull distribution; 0 = one arm only."""
    ns = [int((stats.get(a) or {}).get("n", 0)) for a in arm_list]
    tot = sum(ns)
    if not tot:
        return 0.0
    return round(-sum((n / tot) * math.log2(n / tot) for n in ns if n), 4)


# ---- LinUCB (disjoint), pure python Sherman-Morrison; d = len(FEATURES)

def lin_new(d: int) -> Dict[str, Any]:
    return {"A_inv": [[1.0 if i == j else 0.0 for j in range(d)] for i in range(d)], "b": [0.0] * d, "n": 0}


def _mv(m: List[List[float]], v: Sequence[float]) -> List[float]:
    return [sum(r[j] * v[j] for j in range(len(v))) for r in m]


def lin_score(model: Dict[str, Any], x: Sequence[float], alpha: float = 1.0) -> float:
    ainv, b = model["A_inv"], model["b"]
    theta = _mv(ainv, b)
    ax = _mv(ainv, x)
    return sum(t * xi for t, xi in zip(theta, x, strict=True)) + alpha * math.sqrt(max(0.0, sum(xi * a for xi, a in zip(x, ax, strict=True))))


def lin_update(model: Dict[str, Any], x: Sequence[float], r: float) -> None:
    ainv = model["A_inv"]
    ax = _mv(ainv, x)
    denom = 1.0 + sum(xi * a for xi, a in zip(x, ax, strict=True))
    d = len(x)
    model["A_inv"] = [[ainv[i][j] - ax[i] * ax[j] / denom for j in range(d)] for i in range(d)]
    model["b"] = [bi + r * xi for bi, xi in zip(model["b"], x, strict=True)]
    model["n"] = int(model.get("n", 0)) + 1


def features(goal: Optional[Dict[str, Any]], tries: int = 0) -> List[float]:
    g = goal or {}
    via = str(g.get("via") or "")
    return [1.0,
            1.0 if str(g.get("error_kind") or "") == "AssertionError" else 0.0,
            1.0 if via == "sbfl" else 0.0,
            1.0 if via in ("frame", "frame_assign", "import_error") else 0.0,
            1.0 if g.get("kind") == "lint" else 0.0,
            1.0 if tries > 0 else 0.0,
            float(g.get("tractability") or 0.5)]


# ---- factored arms: one name "f:<style>.<ctx>.<retry>", one posterior per factor level

def factored_select(stats: Dict[str, Dict[str, float]], rng: random.Random) -> str:
    parts = []
    for fac, levels in FACTORS.items():
        draws = {lv: rng.betavariate(1 + (stats.get(f"{fac}={lv}") or {}).get("s", 0.0),
                                     1 + (stats.get(f"{fac}={lv}") or {}).get("f", 0.0)) for lv in levels}
        parts.append(max(levels, key=lambda lv: draws[lv]))
    return "f:" + ".".join(parts)


def factored_levels(arm: str) -> List[str]:
    vals = arm[2:].split(".")
    return [f"{fac}={v}" for fac, v in zip(FACTORS, vals, strict=False)]


def factored_update(stats: Dict[str, Dict[str, float]], arm: str, reward01: int, secs: float = 0.0,
                    g: float = 1.0) -> None:
    if g < 1.0:
        for c in stats.values():
            c["s"] = float(c.get("s", 0.0)) * g
            c["f"] = float(c.get("f", 0.0)) * g
    for lv in factored_levels(arm):
        update(stats, lv, reward01, secs, g=1.0)


def factored_behaviour(arm: str):
    """ArmBehaviour for a factored arm name; None if the name is not factored."""
    if not str(arm).startswith("f:"):
        return None
    from core.learning import ArmBehaviour

    try:
        style, ctx, _retry = arm[2:].split(".")
    except ValueError:
        return None
    return ArmBehaviour(prompt_addon=STYLE_ADDON.get(style, ""), use_workspace_context=ctx != "none",
                        use_experience=ctx != "none", use_few_shot=ctx != "none", force_repo_map=ctx == "map")


def tries_for(arm: str) -> int:
    """Edit attempts per goal for an arm: repair_heavy and f:*.2 get the failure as feedback once."""
    arm = str(arm or "")
    if arm == "repair_heavy":
        return 2
    if arm.startswith("f:") and arm.endswith(".2"):
        return 2
    return 1


# ---------------------------------------------------------------- live state

def state_path(root: Path, kind: str) -> Path:
    return Path(root) / "memory" / "learning" / f"bandit4_{kind}.json"


def load(root: Path, kind: str) -> Dict[str, Any]:
    from core.spine.state_io import read_json

    data = read_json(state_path(root, kind), {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema", 1)
    data.setdefault("buckets", {})
    data.setdefault("lin", {})
    data.setdefault("fact", {})
    return data


def save(root: Path, kind: str, data: Dict[str, Any]) -> None:
    from core.spine.state_io import write_json

    buckets = data.get("buckets") or {}
    if len(buckets) > MAX_BUCKETS:  # keep the most-pulled buckets
        keep = sorted(buckets, key=lambda b: -sum(int(c.get("n", 0)) for c in buckets[b].values()))[:MAX_BUCKETS]
        data["buckets"] = {b: buckets[b] for b in keep}
    allowed = set(arms())
    for b, cells in list((data.get("buckets") or {}).items()):
        data["buckets"][b] = {a: c for a, c in cells.items() if a in allowed or a.startswith("f:")}
    data["lin"] = {a: m for a, m in (data.get("lin") or {}).items() if a in allowed}
    data["updated"] = datetime.now(timezone.utc).isoformat()
    write_json(state_path(root, kind), data)


def choose(root: Path, kind: str, bucket: str, goal: Optional[Dict[str, Any]] = None,
           rng: Optional[random.Random] = None, tries: int = 0) -> Tuple[str, float, str, Dict[str, Any]]:
    """(arm, propensity, reason, trace) for a real goal under the configured selector."""
    name = algo(kind)
    rng = rng or random.Random()
    data = load(root, kind)
    arm_list = arms()
    trace: Dict[str, Any] = {"algo": name}
    if "exemplar" in arm_list:
        try:
            from core.agent import exemplars

            eligible = exemplars.available(root, goal)
        except Exception:
            eligible = False
        trace["exemplar_eligible"] = eligible  # A/B: compare arms only on attempts where both could run
        if not eligible:
            arm_list = [a for a in arm_list if a != "exemplar"]  # no candidate: do not waste the pull
    if factored():
        stats = data["fact"].setdefault(bucket, {})
        arm = factored_select(stats, rng)
        return arm, 1.0, "factored", {**trace, "algo": "factored"}
    if name == "linucb":
        x = features(goal, tries)
        scores = {a: lin_score(data["lin"].get(a) or lin_new(len(x)), x) for a in arm_list}
        best = max(scores.values())
        arm = rng.choice([a for a in arm_list if scores[a] >= best - 1e-12])
        return arm, 1.0, "linucb", {**trace, "x": [round(v, 3) for v in x]}
    stats = data["buckets"].setdefault(bucket, {})
    arm, reason = select(name, stats, arm_list, rng, cost_aware())
    seed = rng.randrange(1 << 30)
    prop = propensity(name, stats, arm_list, arm, seed=seed, cost=cost_aware())
    if cost_aware():
        trace["cost"] = True
    return arm, prop, reason, trace


def record(root: Path, kind: str, bucket: str, arm: str, reward01: int, secs: float = 0.0,
           goal: Optional[Dict[str, Any]] = None, tries: int = 0) -> Dict[str, Any]:
    """Credit one honest-gate outcome. reward01 is 1 only for tests_ok with 0 regressions."""
    if kind not in ("fix_test", "lint"):
        return {"skipped": True}
    data = load(root, kind)
    if str(arm).startswith("f:"):
        factored_update(data["fact"].setdefault(bucket, {}), arm, reward01, secs, gamma())
    else:
        update(data["buckets"].setdefault(bucket, {}), arm, reward01, secs, gamma())
        x = features(goal, tries)
        model = data["lin"].get(arm) or lin_new(len(x))
        lin_update(model, x, float(reward01))
        data["lin"][arm] = model
    save(root, kind, data)
    return {"arm": arm, "reward01": int(reward01)}


def summary(root: Path, kinds: Iterable[str] = ("fix_test", "lint")) -> Dict[str, Any]:
    """Published view (learning_summary.json): per kind, per bucket, per arm. Numbers only."""
    out: Dict[str, Any] = {"algo": {k: algo(k) for k in kinds}, "gamma": gamma(), "cost_aware": cost_aware(),
                           "factored": factored(), "arms": arms()}
    for kind in kinds:
        data = load(root, kind)
        rows = {}
        for bucket, stats in sorted((data.get("buckets") or {}).items())[:MAX_BUCKETS]:
            arm_list = [a for a in arms() if a in stats] or arms()
            rows[bucket] = {
                "entropy_bits": entropy(stats, arms()),
                "arms": {a: {"n": int(c.get("n", 0)), "passes": int(c.get("passes", 0)),
                             "post_mean": round(mean(c), 3),
                             "secs_per_pull": round(float(c.get("secs", 0.0)) / max(1, int(c.get("n", 0))), 1)}
                         for a, c in sorted(stats.items()) if a in arm_list},
            }
            if len(arm_list) > 1:
                rows[bucket]["p_best"] = {a: round(propensity("thompson", stats, arm_list, a, seed=7, draws=400), 3)
                                          for a in arm_list}
        out[kind] = rows
    return out
