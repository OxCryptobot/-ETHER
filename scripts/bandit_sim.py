"""Offline bandit comparison for ETHER real goals (batch 4). Fixed seeds, CPU only.

    python scripts/bandit_sim.py --seeds 200 --out docs/results/batch4/bandit_sim.json
    python scripts/bandit_sim.py --replay memory/learning/trajectories.jsonl

The environment is synthetic but calibrated to what is known on 2026-11-20:
- goal mix from config/goal_seed.json (31 sbfl, 19 test_import, 1 import_error, 4 lint);
- cost from batch 2/3 measurements: ~8 s of guard runs per attempt plus one 4B call
  (assumed 30 s on the 1650; no_context prompts ~0.7x, repo-map prompts ~1.1x);
  repair_heavy (and factored retry=2) pays a second call + gate when the first fails;
- honest pass rates are unknown for the 4B on real goals (the live host never ran them),
  so every scenario is a stated assumption, from "low" (best arm 13% per try) to "mid".
The selectors are the shipped code: core.agent.bandit.select/update (thompson, ucb,
discounted), LinUCB (lin_score/lin_update), factored_select, plus an exact port of
core.learning.BanditPolicy (epsilon-greedy, 0.75/-0.9 reward, prior weight 2, hints).
Promotion is simulated with the live rule (core.agent.outcome.maybe_promote: >= 3 honest
passes, last pull a pass, score > incumbent + 0.05) and with the posterior rule
(>= 3 passes and P(arm > incumbent) >= 0.9).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
import zlib
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agent import bandit as B  # noqa: E402

GUARD_S = 8.0
MODEL_S = 30.0
PROMPT_X = {"no_context": 0.7, "repo_map_on": 1.1, "multifile": 1.15}
VIA_MIX = (("sbfl", 31), ("test_import", 19), ("frame", 1), ("lint", 4))
ARMS5 = list(B.REAL_ARMS)
ARMS7 = ARMS5 + ["with_asserts", "multifile"]
PASS_R, FAIL_R = 0.75, -0.9  # core.learning.compute_reward for the honest pass / fail rows

# per-try pass probability; repair_heavy's second try (with the failure) succeeds with RETRY_X * q
RETRY_X = 0.6
LOW = {"default": .10, "minimal": .09, "repair_heavy": .10, "no_context": .04, "repo_map_on": .13,
       "with_asserts": .07, "multifile": .03}


def _scale(d: Dict[str, float], k: float) -> Dict[str, float]:
    return {a: min(0.95, v * k) for a, v in d.items()}


MID = _scale(LOW, 2.5)
CONTEXTUAL = {  # best arm depends on how the goal was localised
    "sbfl": {"default": .06, "minimal": .05, "repair_heavy": .06, "no_context": .02, "repo_map_on": .15,
             "with_asserts": .04, "multifile": .03},
    "test_import": {"default": .20, "minimal": .16, "repair_heavy": .14, "no_context": .06, "repo_map_on": .12,
                    "with_asserts": .10, "multifile": .04},
    "frame": {"default": .25, "minimal": .22, "repair_heavy": .25, "no_context": .08, "repo_map_on": .20,
              "with_asserts": .15, "multifile": .05},
    "lint": {"default": .40, "minimal": .55, "repair_heavy": .35, "no_context": .30, "repo_map_on": .38,
             "with_asserts": .20, "multifile": .10},
}
UNHINTED = {"default": .15, "minimal": .20, "repair_heavy": .08, "no_context": .05, "repo_map_on": .10,
            "with_asserts": .12, "multifile": .03}  # best arm is one batch-2 hints do NOT favour
DRIFT_B = {"default": .12, "minimal": .16, "repair_heavy": .10, "no_context": .03, "repo_map_on": .05,
           "with_asserts": .06, "multifile": .02}

# factored: logit model style + ctx + retry (no interaction) — the case factoring is built for
F_STYLE = {"plain": 0.0, "minimal": -0.1, "defensive": 0.25}
F_CTX = {"file": 0.0, "none": -0.9, "map": 0.35}
F_BASE = -2.2  # ~10% per try for plain/file


def _sig(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


class Env:
    def __init__(self, scenario: str, horizon: int, rng: random.Random):
        self.s, self.T, self.rng = scenario, horizon, rng
        self.vias = [v for v, n in VIA_MIX for _ in range(n)]

    def context(self) -> str:
        return self.rng.choice(self.vias)

    def q(self, arm: str, via: str, t: int) -> float:
        if self.s == "low":
            return LOW[arm]
        if self.s == "mid":
            return MID[arm]
        if self.s == "unhinted":
            return UNHINTED[arm]
        if self.s == "contextual":
            return CONTEXTUAL[via][arm]
        if self.s == "drift":
            return (MID if t < self.T // 2 else DRIFT_B)[arm]
        if self.s == "factored":
            style, ctx, _r = arm[2:].split(".")
            return _sig(F_BASE + F_STYLE[style] + F_CTX[ctx])
        raise ValueError(self.s)

    def tries(self, arm: str) -> int:
        return B.tries_for(arm)

    def p_pass(self, arm: str, via: str, t: int) -> float:
        q = self.q(arm, via, t)
        if self.tries(arm) == 2:
            return 1 - (1 - q) * (1 - RETRY_X * q)
        return q

    def cost_one(self, arm: str) -> float:
        if arm.startswith("f:"):
            x = {"file": 1.0, "none": 0.7, "map": 1.1}[arm[2:].split(".")[1]]
        else:
            x = PROMPT_X.get(arm, 1.0)
        return GUARD_S + MODEL_S * x

    def expected_cost(self, arm: str, via: str, t: int) -> float:
        c = self.cost_one(arm)
        if self.tries(arm) == 2:
            return c + (1 - self.q(arm, via, t)) * (c - GUARD_S / 2)
        return c

    def pull(self, arm: str, via: str, t: int) -> Tuple[int, float]:
        q = self.q(arm, via, t)
        c = self.cost_one(arm)
        if self.rng.random() < q:
            return 1, c
        if self.tries(arm) == 2:
            c += c - GUARD_S / 2
            return (1 if self.rng.random() < RETRY_X * q else 0), c
        return 0, c

    def arms(self, which: str) -> List[str]:
        if self.s == "factored":
            return ["f:%s.%s.%s" % (s, c, r) for s in B.FACTORS["style"] for c in B.FACTORS["ctx"]
                    for r in B.FACTORS["retry"]]
        return ARMS7 if which == "7" else ARMS5


# ---------------------------------------------------------------- policies

class EGreedy:
    """Exact port of core.learning.BanditPolicy.select/score for one bucket."""
    EPS, FLOOR, ANNEAL, PW, HINT = 0.15, 0.02, 25.0, 2.0, 0.15
    HINTED = ("with_asserts", "repair_heavy", "multifile", "repo_map_on")  # repair_logic|complex hints

    def __init__(self, arms: List[str], rng: random.Random):
        self.arms, self.rng = arms, rng
        self.st: Dict[str, Dict[str, Dict[str, float]]] = {}

    def _b(self, ctx: str) -> Dict[str, Dict[str, float]]:
        return self.st.setdefault(ctx, {a: {"n": 0, "tot": 0.0} for a in self.arms})

    def score(self, ctx: str, a: str) -> float:
        b = self._b(ctx)
        n = sum(c["n"] for c in b.values())
        prior = (sum(c["tot"] for c in b.values()) / n if n else 0.0) + (self.HINT if a in self.HINTED else 0.0)
        return (b[a]["tot"] + self.PW * prior) / (b[a]["n"] + self.PW)

    def select(self, ctx: str, via: str) -> str:
        b = self._b(ctx)
        untried = [a for a in self.arms if b[a]["n"] == 0]
        if untried:
            return self.rng.choice(untried)
        sc = {a: self.score(ctx, a) for a in self.arms}
        m = max(sc.values())
        greedy = self.rng.choice([a for a in self.arms if sc[a] >= m - 1e-9])
        n = sum(c["n"] for c in b.values())
        eps = max(self.FLOOR, min(self.EPS, self.EPS / (1 + n / self.ANNEAL)))
        if self.rng.random() < eps:
            return self.rng.choice([a for a in self.arms if a != greedy])
        return greedy

    def update(self, ctx: str, via: str, a: str, r: int, secs: float) -> None:
        c = self._b(ctx)[a]
        c["n"] += 1
        c["tot"] += PASS_R if r else FAIL_R


class Beta:
    def __init__(self, arms: List[str], rng: random.Random, name: str = "thompson", gamma: float = 1.0,
                 cost: bool = False, by_via: bool = False, prior: str = "pooled"):
        self.arms, self.rng, self.name, self.g, self.cost, self.by_via = arms, rng, name, gamma, cost, by_via
        self.prior = prior
        self.st: Dict[str, Dict[str, Dict[str, float]]] = {}

    def key(self, ctx: str, via: str) -> str:
        return ctx + "|" + via if self.by_via else ctx

    def select(self, ctx: str, via: str) -> str:
        return B.select(self.name, self.st.setdefault(self.key(ctx, via), {}), self.arms, self.rng, self.cost,
                        self.prior)[0]

    def update(self, ctx: str, via: str, a: str, r: int, secs: float) -> None:
        B.update(self.st.setdefault(self.key(ctx, via), {}), a, r, secs, self.g)


class Lin:
    def __init__(self, arms: List[str], rng: random.Random, alpha: float = 1.0):
        self.arms, self.rng, self.alpha = arms, rng, alpha
        self.m = {a: B.lin_new(len(B.FEATURES)) for a in arms}

    @staticmethod
    def x(via: str) -> List[float]:
        return B.features({"via": via, "kind": "lint" if via == "lint" else "fix_test",
                           "error_kind": "AssertionError", "tractability": 0.5})

    def select(self, ctx: str, via: str) -> str:
        x = self.x(via)
        sc = {a: B.lin_score(self.m[a], x, self.alpha) for a in self.arms}
        m = max(sc.values())
        return self.rng.choice([a for a in self.arms if sc[a] >= m - 1e-12])

    def update(self, ctx: str, via: str, a: str, r: int, secs: float) -> None:
        B.lin_update(self.m[a], self.x(via), float(r))


class Factored:
    def __init__(self, arms: List[str], rng: random.Random):
        self.rng, self.st = rng, {}

    def select(self, ctx: str, via: str) -> str:
        return B.factored_select(self.st, self.rng)

    def update(self, ctx: str, via: str, a: str, r: int, secs: float) -> None:
        B.factored_update(self.st, a, r, secs)


class Uniform:
    def __init__(self, arms: List[str], rng: random.Random):
        self.arms, self.rng = arms, rng

    def select(self, ctx: str, via: str) -> str:
        return self.rng.choice(self.arms)

    def update(self, *a: Any) -> None:
        pass


ALGOS = {
    "uniform-5": lambda arms, rng: Uniform(arms, rng),
    "egreedy-7 (batch-2 live)": lambda arms, rng: EGreedy(arms, rng),
    "egreedy-5": lambda arms, rng: EGreedy(arms, rng),
    "ucb1-5": lambda arms, rng: Beta(arms, rng, "ucb"),
    "thompson-7": lambda arms, rng: Beta(arms, rng),
    "thompson-5": lambda arms, rng: Beta(arms, rng),
    "thompson-5 beta(1,1)": lambda arms, rng: Beta(arms, rng, prior="uniform"),
    "thompson-5 g=0.98": lambda arms, rng: Beta(arms, rng, gamma=0.98),
    "thompson-5 cost": lambda arms, rng: Beta(arms, rng, cost=True),
    "thompson-5 by-via": lambda arms, rng: Beta(arms, rng, by_via=True),
    "linucb-5": lambda arms, rng: Lin(arms, rng),
}
FACTORED_ALGOS = {
    "uniform-18": lambda arms, rng: Uniform(arms, rng),
    "egreedy-18": lambda arms, rng: EGreedy(arms, rng),
    "thompson-18 flat": lambda arms, rng: Beta(arms, rng),
    "thompson factored": lambda arms, rng: Factored(arms, rng),
}


def arm_set(algo: str, env: Env) -> List[str]:
    if env.s == "factored":
        return env.arms("f")
    return env.arms("7" if algo.split()[0].endswith("-7") else "5")


# ---------------------------------------------------------------- promotion (live rule and posterior rule)

class Promo:
    def __init__(self, rule: str):
        self.rule, self.inc = rule, "default"
        self.old: Dict[str, Dict[str, float]] = {}
        self.beta: Dict[str, Dict[str, float]] = {}
        self.hist: Dict[str, List[int]] = {}
        self.events: List[Tuple[int, str]] = []

    def _score(self, a: str) -> float:
        n = sum(c["n"] for c in self.old.values())
        prior = sum(c["tot"] for c in self.old.values()) / n if n else 0.0
        c = self.old.get(a) or {"n": 0, "tot": 0.0}
        return (c["tot"] + 2.0 * prior) / (c["n"] + 2.0)

    def step(self, t: int, a: str, r: int) -> None:
        c = self.old.setdefault(a, {"n": 0, "tot": 0.0})
        c["n"] += 1
        c["tot"] += PASS_R if r else FAIL_R
        B.update(self.beta, a, r)
        self.hist.setdefault(a, []).append(r)
        h = self.hist.get(self.inc, [])
        if self.inc != "default" and len(h) >= 3 and not any(h[-3:]):
            self.events.append((t, "demote:" + self.inc))
            self.inc = "default"
        best, bs = None, None
        for arm, rows in self.hist.items():
            if arm == self.inc or sum(rows) < 3 or rows[-1] != 1:
                continue
            if self.rule == "score":
                s = self._score(arm)
                ok = s > self._score(self.inc) + 0.05
            else:
                s = B.prob_better(self.beta, arm, self.inc, seed=t, draws=400)
                ok = s >= B.PROMOTE_PROB
            if ok and (bs is None or s > bs):
                best, bs = arm, s
        if best:
            self.events.append((t, "promote:" + best))
            self.inc = best


# ---------------------------------------------------------------- run

def run_one(args: Tuple[str, str, int, int]) -> Dict[str, Any]:
    scenario, algo, horizon, seed = args
    rng = random.Random(seed * 7919 + zlib.crc32(algo.encode()) % 1000)
    env = Env(scenario, horizon, random.Random(seed))
    arms = arm_set(algo, env)
    table = FACTORED_ALGOS if scenario == "factored" else ALGOS
    pol = table[algo](arms, rng)
    promos = {r: Promo(r) for r in ("score", "posterior")}
    regret = kept = 0.0
    secs = 0.0
    counts: Dict[str, int] = {}
    late: Dict[str, int] = {}
    pool = env.arms("f") if scenario == "factored" else ARMS7
    for t in range(horizon):
        via = env.context()
        ctx = "repair_logic|complex"
        a = pol.select(ctx, via)
        best = max(env.p_pass(x, via, t) for x in pool)
        regret += best - env.p_pass(a, via, t)
        r, c = env.pull(a, via, t)
        kept += r
        secs += c
        counts[a] = counts.get(a, 0) + 1
        if t >= horizon * 3 // 4:
            late[a] = late.get(a, 0) + 1
        pol.update(ctx, via, a, r, c)
        for p in promos.values():
            p.step(t, a, r)
    # the true best arm overall (averaged over the goal mix, second half for drift)
    t_eval = horizon - 1
    vias = env.vias
    true_val = {x: sum(env.p_pass(x, v, t_eval) for v in vias) / len(vias) for x in pool}
    top = max(true_val.values())
    tail = late
    most = max(tail, key=tail.get) if tail else None
    out = {"regret": regret, "kept": kept, "secs": secs, "entropy": _entropy(counts),
           "locked_wrong": int(most is not None and true_val[most] < top - 0.01)}
    for name, p in promos.items():
        first_good = next((t for t, e in p.events if e.startswith("promote:")
                           and true_val[e.split(":", 1)[1]] >= top - 0.01), None)
        bad = sum(1 for t, e in p.events if e.startswith("promote:")
                  and true_val[e.split(":", 1)[1]] < true_val["default" if "default" in true_val else pool[0]])
        out[f"ttp_{name}"] = first_good
        out[f"wrong_{name}"] = bad
        out[f"final_ok_{name}"] = int(true_val.get(p.inc, 0.0) >= top - 0.01)
    return out


def _entropy(counts: Dict[str, int]) -> float:
    tot = sum(counts.values())
    return -sum((n / tot) * math.log2(n / tot) for n in counts.values() if n) if tot else 0.0


def summarize(rows: List[Dict[str, Any]], horizon: int) -> Dict[str, Any]:
    n = len(rows)

    def avg(k: str) -> float:
        return sum(r[k] for r in rows) / n

    def ci(k: str) -> float:
        m = avg(k)
        sd = math.sqrt(sum((r[k] - m) ** 2 for r in rows) / max(1, n - 1))
        return 1.96 * sd / math.sqrt(n)

    out = {
        "regret": round(avg("regret"), 2), "regret_ci95": round(ci("regret"), 2),
        "kept_per_attempt": round(avg("kept") / horizon, 4),
        "kept_per_gpu_hour": round(sum(r["kept"] for r in rows) / (sum(r["secs"] for r in rows) / 3600.0), 3),
        "entropy_bits": round(avg("entropy"), 3),
        "locked_wrong": round(avg("locked_wrong"), 3),
        "regret_p90": round(sorted(r["regret"] for r in rows)[int(0.9 * (n - 1))], 2),
    }
    for rule in ("score", "posterior"):
        hit = [r[f"ttp_{rule}"] for r in rows if r[f"ttp_{rule}"] is not None]
        out[f"promote_{rule}"] = {
            "share_correct_by_T": round(len(hit) / n, 3),
            "median_t": sorted(hit)[len(hit) // 2] if hit else None,
            "wrong_per_run": round(sum(r[f"wrong_{rule}"] for r in rows) / n, 3),
            "final_correct": round(sum(r[f"final_ok_{rule}"] for r in rows) / n, 3),
        }
    return out


def simulate(seeds: int, horizons: List[int], scenarios: List[str], procs: int = 4) -> Dict[str, Any]:
    res: Dict[str, Any] = {}
    jobs = []
    for sc in scenarios:
        table = FACTORED_ALGOS if sc == "factored" else ALGOS
        for h in horizons:
            for algo in table:
                jobs.append((sc, algo, h))
    with Pool(procs) as pool:
        for sc, algo, h in jobs:
            rows = pool.map(run_one, [(sc, algo, h, s) for s in range(seeds)])
            res.setdefault(sc, {}).setdefault(str(h), {})[algo] = summarize(rows, h)
    return res


# ---------------------------------------------------------------- replay of real trajectories

def replay(path: Path) -> Dict[str, Any]:
    """Per-arm honest pass rate (raw and inverse-propensity weighted) and the SNIPS value of
    each algorithm's greedy-at-the-end policy on the logged real-goal rows. Needs logged
    propensities (outcome.record writes them). Few rows = wide error; report n."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("kind") in ("pass", "fail") and (r.get("goal_kind") or "legacy") != "legacy":
            rows.append(r)
    out: Dict[str, Any] = {"rows": len(rows), "arms": {}}
    for r in rows:
        cell = out["arms"].setdefault(r.get("arm"), {"n": 0, "passes": 0, "w": 0.0, "wr": 0.0})
        p = max(1e-3, float(r.get("propensity") or 1.0))
        rew = 1 if r.get("kind") == "pass" and not int(r.get("regressions") or 0) else 0
        cell["n"] += 1
        cell["passes"] += rew
        cell["w"] += 1 / p
        cell["wr"] += rew / p
    for cell in out["arms"].values():
        cell["pass_rate"] = round(cell["passes"] / cell["n"], 4)
        cell["ips_pass_rate"] = round(cell.pop("wr") / cell.pop("w"), 4)
    return out


def snips(rows: List[Dict[str, Any]], target: Dict[str, float]) -> float:
    """Self-normalised IPS value of a stochastic target policy {arm: prob} on logged rows."""
    num = den = 0.0
    for r in rows:
        w = target.get(r["arm"], 0.0) / max(1e-3, float(r["propensity"]))
        num += w * r["reward01"]
        den += w
    return num / den if den else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--horizons", default="200,1000")
    ap.add_argument("--scenarios", default="low,mid,unhinted,contextual,drift,factored")
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--out", default="")
    ap.add_argument("--replay", default="")
    a = ap.parse_args()
    if a.replay:
        print(json.dumps(replay(Path(a.replay)), indent=1))
        return 0
    t0 = time.time()
    res = simulate(a.seeds, [int(h) for h in a.horizons.split(",")], a.scenarios.split(","), a.procs)
    doc = {"seeds": a.seeds, "guard_s": GUARD_S, "model_s": MODEL_S, "retry_x": RETRY_X,
           "secs": round(time.time() - t0, 1), "results": res}
    text = json.dumps(doc, indent=1, sort_keys=True)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
