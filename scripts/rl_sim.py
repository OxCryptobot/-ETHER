"""Batch 8 SIMULATION: finite goal pool (the real config/goal_seed.json, 60 goals) under ETHER's real
attempt limits, comparing arm selectors, goal selectors and sampling-temperature policies.

Everything here is a stated ASSUMPTION about the 4B's pass rates (the live host has never run a real
goal); numbers are for ranking options, not predictions. CPU only, fixed seeds.

    python scripts/rl_sim.py --seeds 300 --out docs/results/batch8/rl_sim.json

Environment (per attempt = one bandit pull, one honest-gate verdict):
- goals: the 60 seed goals with their real via / kind / span / tractability / (file, symbol) target;
- limits from core/agent/goal_source.py: MAX_TRIES=3 per goal, MAX_TARGET_TRIES=6 per SBFL target,
  a kept goal leaves the pool (mark);
- latent per-goal logit  z_g = A + B*(tract-0.25)/0.2 + N(0, SIGMA); a share of goals is unfixable by a
  one-function edit (wrong SBFL suspect / needs more than the target) -> p = 0;
- arm effects on the logit (5 real arms), contextual scenario: effects depend on via / span;
- greedy decoding: at T=0 a repeat of the same arm on the same goal returns the same reply with prob DUP
  (a repeated miss); T>0 draws a fresh reply at a small logit penalty (TEMP_PEN per 1.0 of T);
- cost: GUARD_S + MODEL_S x prompt factor per try (bandit_sim constants); repair_heavy pays a 2nd try
  on a miss with the failure as feedback (logit RETRY_PEN).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
import zlib
from collections import deque
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.agent import bandit as B  # noqa: E402
from scripts.bandit_sim import GUARD_S, MODEL_S, PROMPT_X  # noqa: E402

ARMS = list(B.REAL_ARMS)
MAX_TRIES, MAX_TARGET_TRIES = 3, 6  # goal_source.py:878-879
RETRY_PEN = -0.5
TEMP_PEN = -0.2
TEMPS = (0.0, 0.4, 0.8)
DRIFT_AT = 60  # ~1 h at 60 attempts/h; runs end at ~135 attempts when the pool empties

SCEN = {
    #            A     B    SIGMA  unfixable sbfl / other   DUP
    "low":       (-2.8, 0.5, 1.0, 0.45, 0.25, 0.8),
    "mid":       (-1.8, 0.5, 1.0, 0.35, 0.15, 0.8),
    "contextual": (-1.8, 0.5, 1.0, 0.35, 0.15, 0.8),
    "low_dup03": (-2.8, 0.5, 1.0, 0.45, 0.25, 0.3),
    "mid_dup03": (-1.8, 0.5, 1.0, 0.35, 0.15, 0.3),
    "drift":     (-1.8, 0.5, 1.0, 0.35, 0.15, 0.8),
}
ARM_FX = {"default": 0.0, "minimal": -0.1, "repair_heavy": 0.0, "no_context": -0.9, "repo_map_on": 0.2}


def arm_fx(scen: str, arm: str, g: Dict[str, Any], t: int, horizon: int) -> float:
    if scen == "contextual":
        via, span, lint = g["via"], g["span"], g["kind"] == "lint"
        if arm == "repo_map_on":
            return 0.8 if via == "sbfl" else -0.3
        if arm == "minimal":
            return 0.7 if lint else -0.2
        if arm == "no_context":
            return -0.1 if span else -1.2
        if arm == "repair_heavy":
            return 0.3 if via == "test_import" else -0.2
        return 0.0
    if scen == "drift" and t >= DRIFT_AT:  # e.g. the host pulls code that changes which prompt works
        return {"default": 0.0, "minimal": 0.5, "repair_heavy": -0.2, "no_context": -0.9, "repo_map_on": -0.6}[arm]
    return ARM_FX[arm]


def _sig(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def load_goals() -> List[Dict[str, Any]]:
    seed = json.loads((ROOT / "config/goal_seed.json").read_text(encoding="utf-8"))
    out = []
    for g in seed["goals"].values():
        out.append({"id": g["id"], "via": g.get("via") or ("lint" if g.get("kind") == "lint" else "frame"),
                    "kind": g.get("kind"), "span": bool(g.get("span")), "tract": float(g.get("tractability") or 0),
                    "target": (g["file"], g["symbol"]), "assert": g.get("error_kind") == "AssertionError"})
    return out


GOALS = load_goals()


class World:
    def __init__(self, scen: str, rng: random.Random, horizon: int):
        A, Bc, S, u_sbfl, u_other, dup = SCEN[scen]
        self.scen, self.rng, self.dup, self.T = scen, rng, dup, horizon
        self.z, self.fixable = {}, {}
        for g in GOALS:
            self.z[g["id"]] = A + Bc * (g["tract"] - 0.25) / 0.2 + rng.gauss(0.0, S)
            self.fixable[g["id"]] = rng.random() >= (u_sbfl if g["via"] == "sbfl" else u_other)
        self.tries: Dict[str, int] = {g["id"]: 0 for g in GOALS}
        self.target_tries: Dict[tuple, int] = {}
        self.done: set = set()
        self.seen: Dict[Tuple[str, str], int] = {}  # (goal, arm) -> last outcome at T=0

    def open_goals(self) -> List[Dict[str, Any]]:
        out = []
        for g in GOALS:
            if g["id"] in self.done or self.tries[g["id"]] >= MAX_TRIES:
                continue
            if g["via"] == "sbfl" and self.target_tries.get(g["target"], 0) >= MAX_TARGET_TRIES:
                continue
            out.append(g)
        return out

    def p(self, g: Dict[str, Any], arm: str, t: int, temp: float) -> float:
        if not self.fixable[g["id"]]:
            return 0.0
        return _sig(self.z[g["id"]] + arm_fx(self.scen, arm, g, t, self.T) + TEMP_PEN * temp)

    def attempt(self, g: Dict[str, Any], arm: str, t: int, temp: float) -> Tuple[int, float, float, bool]:
        """(reward01, wall secs, gpu secs, duplicate)"""
        model = MODEL_S * PROMPT_X.get(arm, 1.0)
        secs, gpu, dup = GUARD_S + model, model, False
        key = (g["id"], arm)
        if temp == 0.0 and key in self.seen and self.rng.random() < self.dup:
            r, dup = 0, True  # the same greedy reply again: the same miss
        else:
            r = int(self.rng.random() < self.p(g, arm, t, temp))
        if not r and arm == "repair_heavy":
            secs += model + GUARD_S / 2
            gpu += model
            q = _sig(self.z[g["id"]] + arm_fx(self.scen, arm, g, t, self.T) + RETRY_PEN) if self.fixable[g["id"]] else 0.0
            r = int(self.rng.random() < q)
        if temp == 0.0:
            self.seen[key] = r
        self.tries[g["id"]] += 1
        if g["via"] == "sbfl":
            self.target_tries[g["target"]] = self.target_tries.get(g["target"], 0) + 1
        if r:
            self.done.add(g["id"])
            for o in GOALS:  # siblings on the same target resolved by the same edit (sota keep branch)
                if o["target"] == g["target"] and o["via"] == "sbfl" and g["via"] == "sbfl":
                    self.done.add(o["id"])
        return r, secs, gpu, dup


# ---------------------------------------------------------------- goal selectors

def goal_ranked(w: World, open_: List[Dict[str, Any]], st: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    """goal_source.ranked: tractability - 0.2*own - 0.1*shared."""
    def rank(g):
        own = w.tries[g["id"]]
        shared = sum(w.tries[o["id"]] for o in GOALS if o["target"] == g["target"]) - own
        return (-(g["tract"] - 0.2 * own - 0.1 * shared), g["id"])
    return min(open_, key=rank)


def goal_breadth(w, open_, st, rng):
    """Every open goal once before any goal twice, then by tractability."""
    return min(open_, key=lambda g: (w.tries[g["id"]], -g["tract"], g["id"]))


def goal_random(w, open_, st, rng):
    return rng.choice(open_)


def goal_ts(w, open_, st, rng):
    """Thompson over goals. Prior mean from tractability, strength 2; a miss is a Beta failure.
    Hierarchical: the prior mean is rescaled by the pooled kept rate seen so far (empirical Bayes)."""
    att, kept = st.get("att", 0), st.get("kept", 0)
    scale = ((kept + 1.0) / (att + 2.0)) / 0.25 if att >= 10 else 1.0
    best, bv = None, -1.0
    for g in open_:
        m = min(0.9, max(0.02, (0.05 + 0.6 * g["tract"]) * scale))
        a0, b0 = 2.0 * m, 2.0 * (1 - m)
        f = w.tries[g["id"]]
        v = rng.betavariate(a0, b0 + f)
        if v > bv:
            best, bv = g, v
    return best


GOAL_SEL = {"ranked (live)": goal_ranked, "breadth-first": goal_breadth, "goal-TS (hier)": goal_ts,
            "random": goal_random}


# ---------------------------------------------------------------- arm selectors

def x_rich(g: Dict[str, Any], w: World, exemplar_ok: bool) -> List[float]:
    tries = w.tries[g["id"]]
    return [1.0, 1.0 if g["assert"] else 0.0, 1.0 if g["via"] == "sbfl" else 0.0,
            1.0 if g["via"] in ("frame", "import_error") else 0.0, 1.0 if g["kind"] == "lint" else 0.0,
            tries / 2.0, g["tract"], 1.0 if g["span"] else 0.0, 1.0 if exemplar_ok else 0.0]


class ArmTS:
    def __init__(self, rng, gamma=1.0, window=0, by_via=False):
        self.rng, self.g, self.W, self.by_via = rng, gamma, window, by_via
        self.st: Dict[str, Dict[str, Any]] = {}
        self.hist: Dict[str, deque] = {}

    def key(self, g):
        return (g["kind"] or "") + ("|" + g["via"] if self.by_via else "")

    def select(self, g, w):
        return B.select("thompson", self.st.setdefault(self.key(g), {}), ARMS, self.rng)[0]

    def update(self, g, w, arm, r, secs):
        k = self.key(g)
        if self.W:
            h = self.hist.setdefault(k, deque(maxlen=self.W))
            h.append((arm, r))
            st: Dict[str, Any] = {}
            for a, rr in h:
                B.update(st, a, rr)
            self.st[k] = st
        else:
            B.update(self.st.setdefault(k, {}), arm, r, secs, self.g)


class ArmHier(ArmTS):
    """Per-via cells shrunk to the kind-level pooled rate (two-level Beta, PRIOR_N pseudo-pulls)."""

    def select(self, g, w):
        kind = self.st.setdefault(g["kind"] or "", {})
        cell = self.st.setdefault((g["kind"] or "") + "|" + g["via"], {})
        out = {}
        for a in ARMS:
            ck, cv = kind.get(a) or {}, cell.get(a) or {}
            mk = (1.0 + ck.get("s", 0.0)) / (2.0 + ck.get("s", 0.0) + ck.get("f", 0.0))
            out[a] = self.rng.betavariate(4.0 * mk + cv.get("s", 0.0), 4.0 * (1 - mk) + cv.get("f", 0.0))
        m = max(out.values())
        return self.rng.choice([a for a in ARMS if out[a] >= m - 1e-12])

    def update(self, g, w, arm, r, secs):
        B.update(self.st.setdefault(g["kind"] or "", {}), arm, r)
        B.update(self.st.setdefault((g["kind"] or "") + "|" + g["via"], {}), arm, r)


class ArmLin:
    def __init__(self, rng, alpha=1.0, rich=True):
        self.rng, self.alpha, self.rich = rng, alpha, rich
        self.m = {a: B.lin_new(9 if rich else 7) for a in ARMS}

    def x(self, g, w):
        if self.rich:
            return x_rich(g, w, exemplar_ok=len(w.done) > 0)
        return B.features({"via": g["via"], "kind": g["kind"], "error_kind": "AssertionError" if g["assert"] else "",
                           "tractability": g["tract"]}, w.tries[g["id"]])

    def select(self, g, w):
        x = self.x(g, w)
        sc = {a: B.lin_score(self.m[a], x, self.alpha) for a in ARMS}
        mx = max(sc.values())
        return self.rng.choice([a for a in ARMS if sc[a] >= mx - 1e-12])

    def update(self, g, w, arm, r, secs):
        B.lin_update(self.m[arm], self.x(g, w), float(r))


class ArmUniform:
    def __init__(self, rng):
        self.rng = rng

    def select(self, g, w):
        return self.rng.choice(ARMS)

    def update(self, *a):
        pass


ARM_SEL = {
    "thompson (live)": lambda rng: ArmTS(rng),
    "dTS g=0.98": lambda rng: ArmTS(rng, gamma=0.98),
    "dTS g=0.995": lambda rng: ArmTS(rng, gamma=0.995),
    "SW-TS W=60": lambda rng: ArmTS(rng, window=60),
    "TS by-via": lambda rng: ArmTS(rng, by_via=True),
    "hier TS (via|kind)": lambda rng: ArmHier(rng),
    "LinUCB 7f (bundle)": lambda rng: ArmLin(rng, rich=False),
    "LinUCB 9f rich": lambda rng: ArmLin(rng, rich=True),
    "uniform": lambda rng: ArmUniform(rng),
}


# ---------------------------------------------------------------- temperature policies

class TempFixed:
    def __init__(self, t):
        self.t = t

    def pick(self, g, w, rng):
        return self.t

    def update(self, *a):
        pass


class TempSchedule:
    """T=0 on a goal's first attempt, 0.7 after (ETHER_SAMPLE_TEMP=0,0.7)."""

    def pick(self, g, w, rng):
        return 0.0 if w.tries[g["id"]] == 0 else 0.7

    def update(self, *a):
        pass


class TempBandit:
    """Thompson over T in TEMPS, conditioned on first attempt vs retry."""

    def __init__(self):
        self.st: Dict[str, Dict[str, Any]] = {}

    def pick(self, g, w, rng):
        k = "first" if w.tries[g["id"]] == 0 else "retry"
        arm = B.select("thompson", self.st.setdefault(k, {}), [str(t) for t in TEMPS], rng)[0]
        self._k = k
        return float(arm)

    def update(self, g, w, temp, r):
        B.update(self.st.setdefault(self._k, {}), str(temp), r)


TEMP_POL = {"T=0 (live)": lambda: TempFixed(0.0), "T=0.7 always": lambda: TempFixed(0.7),
            "schedule 0 then 0.7": TempSchedule, "temp bandit {0,.4,.8}": TempBandit}


# ---------------------------------------------------------------- run

def run_one(args) -> Dict[str, Any]:
    scen, goal_name, arm_name, temp_name, horizon, seed = args
    rng = random.Random(seed * 104729 + zlib.crc32(f"{goal_name}|{arm_name}|{temp_name}".encode()) % 9973)
    w = World(scen, random.Random(seed), horizon)
    pick_goal, arms, temps = GOAL_SEL[goal_name], ARM_SEL[arm_name](rng), TEMP_POL[temp_name]()
    st = {"att": 0, "kept": 0}
    kept = secs = gpu = dups = wasted = 0.0
    first = None
    kept60 = None
    counts: Dict[str, int] = {}
    for t in range(horizon):
        open_ = w.open_goals()
        if not open_:
            break
        g = pick_goal(w, open_, st, rng)
        arm = arms.select(g, w)
        temp = temps.pick(g, w, rng)
        wasted += 0 if w.fixable[g["id"]] else 1
        r, s, gs, dup = w.attempt(g, arm, t, temp)
        arms.update(g, w, arm, r, s)
        temps.update(g, w, temp, r)
        st["att"] += 1
        st["kept"] += r
        kept += r
        secs += s
        gpu += gs
        dups += dup
        counts[arm] = counts.get(arm, 0) + 1
        if r and first is None:
            first = t + 1
        if t + 1 == 60:
            kept60 = kept
    n = st["att"]
    tot = sum(counts.values())
    ent = -sum((c / tot) * math.log2(c / tot) for c in counts.values() if c) if tot else 0.0
    return {"kept": kept, "kept60": kept if kept60 is None else kept60, "attempts": n, "secs": secs, "gpu": gpu, "dups": dups, "wasted": wasted,
            "first": first, "entropy": ent, "top_share": max(counts.values()) / tot if tot else 0.0,
            "fixable_goals": sum(1 for v in w.fixable.values() if v)}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    kept = [r["kept"] for r in rows]
    m = sum(kept) / n
    sd = math.sqrt(sum((k - m) ** 2 for k in kept) / max(1, n - 1))
    firsts = sorted(r["first"] for r in rows if r["first"] is not None)
    return {"kept": round(m, 2), "kept_ci95": round(1.96 * sd / math.sqrt(n), 2),
            "kept_at_60_attempts": round(sum(r["kept60"] for r in rows) / n, 2),
            "attempts": round(sum(r["attempts"] for r in rows) / n, 1),
            "kept_per_attempt": round(sum(kept) / max(1, sum(r["attempts"] for r in rows)), 4),
            "kept_per_gpu_hour": round(sum(kept) / (sum(r["gpu"] for r in rows) / 3600.0), 2),
            "dup_share": round(sum(r["dups"] for r in rows) / max(1, sum(r["attempts"] for r in rows)), 3),
            "wasted_share": round(sum(r["wasted"] for r in rows) / max(1, sum(r["attempts"] for r in rows)), 3),
            "first_keep_median": firsts[len(firsts) // 2] if firsts else None,
            "no_keep_runs": round(sum(1 for r in rows if r["first"] is None) / n, 3),
            "arm_entropy": round(sum(r["entropy"] for r in rows) / n, 3),
            "top_share": round(sum(r["top_share"] for r in rows) / n, 3),
            "fixable_goals": round(sum(r["fixable_goals"] for r in rows) / n, 1)}


EXPERIMENTS = {
    "E1 arm selectors (ranked goals, T=0)": [("ranked (live)", a, "T=0 (live)") for a in ARM_SEL],
    "E2 goal selectors (thompson arms, T=0)": [(g, "thompson (live)", "T=0 (live)") for g in GOAL_SEL],
    "E3 sampling temperature (ranked, thompson)": [("ranked (live)", "thompson (live)", t) for t in TEMP_POL],
    "E4 combined": [("ranked (live)", "thompson (live)", "T=0 (live)"),
                    ("goal-TS (hier)", "thompson (live)", "schedule 0 then 0.7"),
                    ("breadth-first", "thompson (live)", "schedule 0 then 0.7"),
                    ("goal-TS (hier)", "hier TS (via|kind)", "schedule 0 then 0.7")],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--horizon", type=int, default=400, help="attempt budget; runs stop earlier when the pool empties")
    ap.add_argument("--scenarios", default="low,mid,contextual,drift,low_dup03,mid_dup03")
    ap.add_argument("--procs", type=int, default=6)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    t0 = time.time()
    res: Dict[str, Any] = {}
    with Pool(a.procs) as pool:
        for exp, combos in EXPERIMENTS.items():
            for sc in a.scenarios.split(","):
                if exp.startswith(("E1", "E2")) and sc.endswith("dup03"):
                    continue
                for gname, aname, tname in combos:
                    rows = pool.map(run_one, [(sc, gname, aname, tname, a.horizon, s) for s in range(a.seeds)])
                    res.setdefault(exp, {}).setdefault(sc, {})[f"{gname} / {aname} / {tname}"] = summarize(rows)
    doc = {"label": "SIMULATION (assumed pass rates; not host data)", "seeds": a.seeds, "horizon": a.horizon,
           "scenarios": {k: dict(zip(("A", "B", "sigma", "unfixable_sbfl", "unfixable_other", "dup"), v))
                         for k, v in SCEN.items()},
           "limits": {"MAX_TRIES": MAX_TRIES, "MAX_TARGET_TRIES": MAX_TARGET_TRIES}, "guard_s": GUARD_S,
           "model_s": MODEL_S, "temp_pen": TEMP_PEN, "retry_pen": RETRY_PEN, "goals": len(GOALS),
           "secs": round(time.time() - t0, 1), "results": res}
    text = json.dumps(doc, indent=1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
