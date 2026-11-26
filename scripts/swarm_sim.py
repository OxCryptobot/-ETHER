#!/usr/bin/env python3
"""Offline simulation of practical swarm-agent designs for ETHER.

This is a SIMULATION with stated, live-calibrated assumptions — not a 1650
measurement of a swarm (no swarm has run on the host). Live calibration is
taken from artifacts/learning_summary.json generated 2026-11-26T17:47:48Z
on origin main: real_graded=238, real_passes=2, gpu_hours=14.903,
kept_per_gpu_hour=0.134, dup_share=0.1846, by_via sbfl 133/0, test_import 87/2,
lint 12/0, import_error 3/0, test_import_assign 3/0.

    python scripts/swarm_sim.py --seeds 200 --out docs/results/swarm/swarm_sim.json

Reward is always honest-gate 0/1: a keep is recorded only after an after-edit
guard run (T_AFTER). Pregates, critics, and debate judges may only veto or
rank; they never award a PASS. Model calls are serial (one 4B on the 1650).

Cost anatomy, measured against live attempt wall times (see docs/SWARM_DESIGN.md):

    baseline pytest  ->  T_BASE ~ 160s   (always paid; cannot be skipped by a
                                          critic of the *edit* — there is no
                                          edit yet; sota._attempt_real)
    4B proposer      ->  T_MODEL ~ 30s   (planning number, same as bandit_sim /
                                          marl_sim)
    after-edit guard ->  T_AFTER ~ 55s   (paid only when an edit is gated;
                                          live regression attempts ~245 s =
                                          160+30+55)
    CPU prefilter    ->  T_PRE ~ 2s

The live mean 225.45 s/attempt also includes baseline-timeout aborts (~185 s,
no model). Batch 10 item 0 classifies those as no_attempt, so the post-batch-10
baseline used here is the completed-attempt cost, not the 225 s blend.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Live calibration (origin main learning_summary, 2026-11-26T17:47:48Z)
# ---------------------------------------------------------------------------

LIVE_GENERATED = "2026-11-26T17:47:48.106641+00:00"
LIVE_REAL_GRADED = 238
LIVE_REAL_PASSES = 2
LIVE_GPU_HOURS = 14.903
LIVE_KEPT_PER_GPU_HOUR = 0.134
LIVE_DUP_SHARE = 0.1846
LIVE_REVERT_RATE = 0.1681
LIVE_REGRESSIONS = 22
LIVE_FILLER_RATE = 0.9556  # among ALL kept rows, including 43 legacy filler keeps
LIVE_OPEN = 95
LIVE_DRY_S = 160396.0  # host health: no learning attempt for 160396 s
LIVE_SECS_PER_ATTEMPT = LIVE_GPU_HOURS * 3600.0 / LIVE_REAL_GRADED  # 225.4487...

VIA_N = {
    "sbfl": 133,
    "test_import": 87,
    "lint": 12,
    "import_error": 3,
    "test_import_assign": 3,
}
VIA_KEEP = {
    "sbfl": 0,
    "test_import": 2,
    "lint": 0,
    "import_error": 0,
    "test_import_assign": 0,
}
VIA_NAMES = tuple(VIA_N.keys())
MAX_TRIES = 3

# Cost model (seconds). Stated assumptions, fitted to completed-attempt times.
T_BASE = 160.0
T_MODEL = 30.0
T_AFTER = 55.0
T_PRE = 2.0

# Fractions we cannot read from the 238-row totals (recent-25 is timeout-biased).
# Stated: 20% of model replies never reach the after-gate (no_function / no_edit).
P_NO_EDIT = 0.20
# Deterministic prefilter (AST/LSP/lint/security) veto rate on would-fail edits
# that *would have been gated*. False-reject rate on would-keeps. Assumptions.
P_PRE_VETO = 0.12
P_PRE_KILL = 0.01
# 4B critic: higher veto, much higher false-reject (weak test predictor).
P_CRITIC_VETO = 0.30
P_CRITIC_KILL = 0.08
# Localizer: fraction of sbfl mass that inherits test_import keep rate.
# Default 0.15 is conservative; 0 and 0.40 are sensitivity cases.
LOC_FRAC = 0.15
# Planted-bug keep rate (single-site, validated mutant). Assumption, not measured.
P_PLANTED = 0.08
# Temperature-ladder duplicate rate (ETHER_SAMPLE_TEMP=0,0.7). Assumption;
# live dup_share 0.1846 is at T=0 only (77 attempts recorded temp=0.0).
DUP_TEMP = 0.08
# Goal-flow mix (option 6): reweight toward the only via that has kept.
FLOW_SHARE = {
    "sbfl": 0.20,
    "test_import": 0.70,
    "lint": 0.08,
    "import_error": 0.01,
    "test_import_assign": 0.01,
}


def clip01(p: float) -> float:
    return min(1.0, max(0.0, p))


def mle_rates() -> Dict[str, float]:
    return {v: VIA_KEEP[v] / VIA_N[v] for v in VIA_NAMES}


def laplace_rates() -> Dict[str, float]:
    """Jeffreys/Laplace (k+0.5)/(n+1), lint capped at the test_import MLE.

    Raw Laplace for lint (0/12) is 0.038, which would outrank the only via
    that has actually kept (test_import 0.023). That is not a measurement;
    we cap it so the prior cannot invent a lint ranking the data does not
    support.
    """
    import_p = (VIA_KEEP["test_import"] + 0.5) / (VIA_N["test_import"] + 1)
    out = {v: (VIA_KEEP[v] + 0.5) / (VIA_N[v] + 1) for v in VIA_NAMES}
    out["lint"] = min(out["lint"], import_p)
    return out


def shares(weights: Dict[str, float]) -> Dict[str, float]:
    z = sum(weights.values())
    return {k: weights[k] / z for k in weights}


LIVE_SHARE = shares({v: float(VIA_N[v]) for v in VIA_NAMES})


def live_p(rates: Dict[str, float], mix: Optional[Dict[str, float]] = None) -> float:
    mix = mix or LIVE_SHARE
    return sum(mix[v] * rates[v] for v in VIA_NAMES)


def live_replay_gpuh() -> float:
    """Identity: 2 keeps / 14.903 h = 0.134 kept per GPU-hour (rounded)."""
    return LIVE_REAL_PASSES / LIVE_GPU_HOURS


# ---------------------------------------------------------------------------
# Scenario priors
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    name: str
    rates: Dict[str, float]
    loc_frac: float
    t_base: float
    t_model: float
    t_after: float
    dup: float
    p_no_edit: float
    sparse: bool
    p_easy: float
    note: str

    def p_of(self, via: str, loc: bool = False) -> float:
        p = self.rates[via]
        if loc and via == "sbfl" and self.loc_frac > 0:
            p = p + self.loc_frac * (self.rates["test_import"] - p)
        return clip01(p)

    def easy_frac(self, via: str, loc: bool = False) -> Tuple[float, float]:
        """For sparse: (fraction of goals that are solvable, p when solvable).

        Calibrated so the mixture mean equals p_of(via). Unsolvable goals
        stay at p=0 no matter how many samples you take — the pessimistic
        reading of '2 keeps in 238 attempts'.
        """
        mean = self.p_of(via, loc=loc)
        if not self.sparse:
            return 1.0, mean
        if mean <= 0.0:
            return 0.0, 0.0
        pe = max(self.p_easy, mean)
        return clip01(mean / pe), pe


def build_scenarios() -> Dict[str, Scenario]:
    mle = mle_rates()
    lap = laplace_rates()
    common = dict(t_base=T_BASE, t_model=T_MODEL, t_after=T_AFTER, dup=LIVE_DUP_SHARE,
                  p_no_edit=P_NO_EDIT, p_easy=0.30)
    return {
        "homogeneous": Scenario(
            "homogeneous", mle, LOC_FRAC, **common, sparse=False,
            note="MLE keep rate per via (sbfl/lint/other = 0). Loc lift 0.15 when the option has a localizer.",
        ),
        "sparse": Scenario(
            "sparse", mle, LOC_FRAC, **common, sparse=True,
            note="Mean p matches MLE, but only a small easy subset is solvable (p_easy=0.30). Best-of-N cannot unlock the rest.",
        ),
        "laplace": Scenario(
            "laplace", lap, LOC_FRAC, **common, sparse=False,
            note="(k+0.5)/(n+1) prior, lint capped at test_import. Sensitivity only — not a measurement.",
        ),
        "loc_off": Scenario(
            "loc_off", mle, 0.0, **common, sparse=False,
            note="Same as homogeneous but localizer lift is forced to 0 (SBFL stays at 0/133).",
        ),
        "loc_strong": Scenario(
            "loc_strong", mle, 0.40, **common, sparse=False,
            note="Optimistic localizer: 40% of sbfl mass inherits the test_import keep rate.",
        ),
        "high_dup": Scenario(
            "high_dup", mle, LOC_FRAC, t_base=T_BASE, t_model=T_MODEL, t_after=T_AFTER,
            dup=0.40, p_no_edit=P_NO_EDIT, sparse=False, p_easy=0.30,
            note="Duplicate-reply share 0.40 (worse than live 0.1846). Best-of-N at T=0 collapses.",
        ),
        "cheap_after": Scenario(
            "cheap_after", mle, LOC_FRAC, t_base=T_BASE, t_model=T_MODEL, t_after=8.0,
            dup=LIVE_DUP_SHARE, p_no_edit=P_NO_EDIT, sparse=False, p_easy=0.30,
            note="After-gate only 8 s (batch-4 planning number). Pregates and critics save almost nothing.",
        ),
        "expensive_model": Scenario(
            "expensive_model", mle, LOC_FRAC, t_base=T_BASE, t_model=90.0, t_after=T_AFTER,
            dup=LIVE_DUP_SHARE, p_no_edit=P_NO_EDIT, sparse=False, p_easy=0.30,
            note="Each 4B call is 90 s. Extra-call options (BoN, critic, debate, MoA) get more expensive.",
        ),
    }


# ---------------------------------------------------------------------------
# Option policies
# ---------------------------------------------------------------------------

# kind: how the option spends model calls and the gate
# loc: whether SBFL keep rate is lifted
# flow: whether the via mix is reweighted
# refill: planted goals when the real pool is dry
# n_propose: proposer samples per attempt (serial)
# extra_roles: additional 4B calls per attempt (critic / debate / aggregator)
# det_veto / llm_veto: after-gate skip rates (and keep-kill rates)
# diverse: use DUP_TEMP instead of scenario.dup for uniqueness
# planted_mix: probability an attempt is planted while the real pool is still open

@dataclass(frozen=True)
class Option:
    name: str
    title: str
    loc: bool = False
    flow: bool = False
    refill: bool = False
    n_propose: int = 1
    extra_roles: int = 0
    det_veto: bool = False
    llm_veto: bool = False
    diverse: bool = False
    planted_mix: float = 0.0
    hier: bool = False
    note: str = ""


OPTIONS: List[Option] = [
    Option("baseline", "Baseline (post-batch-10, flags off)",
           note="One 4B proposer, live via mix, no pregate, no dedup skip, no scouts, no planted."),
    Option("zero_model", "1. Zero-model-call gem swarm",
           loc=True, det_veto=True,
           note="SBFL/LSP localizer, security+AST+LSP pregate, dedup skip, test-selector as context only."),
    Option("hier_bag", "2. Hierarchical bag-of-decisions",
           loc=False, hier=True,
           note="Top Thompson over mix vs prefer-import; lower Thompson over 5 prompt arms. No extra model call."),
    Option("critic_4b", "3a. Proposer → 4B critic (veto only)",
           extra_roles=1, llm_veto=True,
           note="One extra 4B call; critic may only veto. Never a PASS."),
    Option("critic_det", "3b. Proposer → deterministic critic (veto only)",
           det_veto=True,
           note="Same veto as the gem pregate; no extra model call. Overlaps option 1 without the localizer."),
    Option("bon2", "4. Best-of-2 + deterministic prefilters",
           n_propose=2, det_veto=True, diverse=True,
           note="One baseline, two serial 4B samples, prefilter picks at most one to gate."),
    Option("bon4", "4. Best-of-4 + deterministic prefilters",
           n_propose=4, det_veto=True, diverse=True,
           note="Same as BoN=2 with four serial samples."),
    Option("planted", "5. Planted-bug proposer/solver curriculum",
           refill=True, planted_mix=0.25,
           note="When the real pool is open, 25% planted; when dry, 100% planted. Credit only from later kept solves."),
    Option("goal_flow", "6. Goal-flow scouts (no model calls)",
           flow=True, refill=True,
           note="Deterministic scouts refill and reweight the queue toward test_import; planted when dry."),
    Option("zero_plus_flow", "1+6. Gems + goal-flow (recommended)",
           loc=True, det_veto=True, flow=True, refill=True,
           note="Recommended next-batch default: deterministic agents + scouts, one 4B proposer."),
    Option("zero_flow_bon2", "1+6+4. Gems + flow + BoN=2",
           loc=True, det_veto=True, flow=True, refill=True, n_propose=2, diverse=True,
           note="Recommended second flag: turn on after the queue is flowing if GPU-hour stays healthy."),
    Option("debate", "7a. Two-role debate + 4B judge (reject)",
           extra_roles=2, n_propose=1, llm_veto=True,
           note="Proposer + critic + judge = 3 serial 4B calls. Judge may only veto. Small assumed lift is not used; p stays the coverage of one proposal (debate is not BoN)."),
    Option("moa", "7b. Mixture-of-agents, 4 proposers + aggregator (reject)",
           n_propose=4, extra_roles=1, det_veto=True, diverse=True,
           note="4 serial proposers + 1 aggregator call. Aggregator may pick a worse candidate; modelled as 0.9×pass@unique."),
    Option("evo_prompt", "7c. Population / prompt-evolution (reject)",
           hier=False,
           note="Eight prompt variants as arms; same p as baseline, more exploration waste at n≈2 keeps."),
]


# ---------------------------------------------------------------------------
# Attempt mechanics
# ---------------------------------------------------------------------------

def _unique_samples(n: int, dup: float, rng: random.Random) -> int:
    """How many distinct proposals in n serial samples with duplicate rate `dup`."""
    if n <= 0:
        return 0
    u = 1
    for _ in range(n - 1):
        if rng.random() >= dup:
            u += 1
    return u


def _bernoulli_or(p: float, n: int, rng: random.Random) -> bool:
    if n <= 0 or p <= 0.0:
        return False
    if p >= 1.0:
        return True
    # 1-(1-p)^n, realised by n trials (equivalent, and works for sparse p_easy)
    for _ in range(n):
        if rng.random() < p:
            return True
    return False


def pick_via(mix: Dict[str, float], rng: random.Random) -> str:
    r = rng.random()
    acc = 0.0
    last = VIA_NAMES[-1]
    for v in VIA_NAMES:
        acc += mix[v]
        if r <= acc:
            return v
        last = v
    return last


def mix_for(opt: Option, rates: Dict[str, float], rng: Optional[random.Random] = None,
            hier_state: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    if opt.flow:
        return dict(FLOW_SHARE)
    if opt.hier and hier_state is not None and rng is not None:
        # Two policies: live mix vs prefer-import. Thompson over their 0/1 rewards.
        policy = thompson_pick(hier_state, ("live", "prefer"), rng)
        hier_state["_last_policy"] = policy
        if policy == "prefer":
            return dict(FLOW_SHARE)
        return dict(LIVE_SHARE)
    return dict(LIVE_SHARE)


def thompson_pick(state: Dict[str, Any], names: Sequence[str], rng: random.Random) -> str:
    best, best_s = names[0], -1.0
    for n in names:
        cell = state.setdefault(n, {"a": 1.0, "b": 1.0})
        s = rng.gammavariate(cell["a"], 1.0)
        t = rng.gammavariate(cell["b"], 1.0)
        draw = s / (s + t)
        if draw > best_s:
            best, best_s = n, draw
    return best


def thompson_update(state: Dict[str, Any], name: str, reward: int) -> None:
    cell = state.setdefault(name, {"a": 1.0, "b": 1.0})
    if reward:
        cell["a"] += 1.0
    else:
        cell["b"] += 1.0


@dataclass
class Attempt:
    kept: int = 0
    real_kept: int = 0
    planted_kept: int = 0
    secs: float = 0.0
    model_calls: int = 0
    after_gates: int = 0
    after_saved: int = 0
    no_edit: int = 0
    veto: int = 0
    false_reject: int = 0
    planted: int = 0
    via: str = ""
    filler: int = 0  # always 0 for simulated real/planted goals (legacy filler is not requeued)


def run_attempt(opt: Option, scen: Scenario, rng: random.Random,
                via: Optional[str] = None, planted: bool = False,
                hier_state: Optional[Dict[str, Any]] = None,
                solvable: Optional[bool] = None, p_each: Optional[float] = None) -> Attempt:
    """One host_main attempt. Keep only if the after-gate would run and pass."""
    a = Attempt()
    tb, tm, ta = scen.t_base, scen.t_model, scen.t_after
    a.secs += tb  # baseline always paid for a selectable goal
    if planted:
        a.planted = 1
        a.via = "planted"
        ef, ps = (1.0, P_PLANTED) if not scen.sparse else (min(1.0, P_PLANTED / max(scen.p_easy, P_PLANTED)), scen.p_easy)
    else:
        mix = mix_for(opt, scen.rates, rng, hier_state)
        a.via = via or pick_via(mix, rng)
        ef, ps = scen.easy_frac(a.via, loc=opt.loc)
    if solvable is None:
        solvable = rng.random() < ef
    if p_each is None:
        p_each = ps if solvable else 0.0

    n_prop = opt.n_propose
    if opt.name == "evo_prompt":
        n_prop = 1  # still one proposer; more arms only affect the selector (hier)
    a.model_calls = n_prop + opt.extra_roles
    a.secs += a.model_calls * tm
    if opt.det_veto or opt.n_propose > 1:
        a.secs += n_prop * T_PRE

    # Unique coverage of the proposer samples.
    dup = DUP_TEMP if opt.diverse else scen.dup
    unique = _unique_samples(n_prop, dup, rng)

    # MoA aggregator may drop a good candidate (0.9×).
    if opt.name == "moa":
        p_each = p_each * 0.9

    would_keep = _bernoulli_or(p_each, unique, rng) if p_each > 0 else False

    # Extract failure only applies to would-misses. Live p_keep already includes
    # no_function / no_edit, so a would-keep is a reply that *was* extractable.
    no_edit = False
    if not would_keep:
        if opt.n_propose <= 1:
            no_edit = rng.random() < scen.p_no_edit
        else:
            no_edit = all(rng.random() < scen.p_no_edit for _ in range(max(1, unique)))
    if no_edit:
        a.no_edit = 1
        if hier_state is not None and opt.hier:
            thompson_update(hier_state, hier_state.get("_last_policy", "live"), 0)
        return a

    # Veto / dedup of a would-fail vs false-reject of a would-keep.
    veto = False
    if would_keep:
        kill = P_PRE_KILL if opt.det_veto else 0.0
        if opt.llm_veto:
            kill = max(kill, P_CRITIC_KILL)
        if kill and rng.random() < kill:
            would_keep = False
            a.false_reject = 1
            veto = True
    else:
        # Dedup skip (option 1 and anything with det_veto): live dup share of fails
        # that already reached the gate once. Approximate: skip after-gate with
        # probability dup on a fail.
        p_veto = 0.0
        if opt.det_veto:
            p_veto = 1.0 - (1.0 - P_PRE_VETO) * (1.0 - scen.dup)
        if opt.llm_veto:
            p_veto = 1.0 - (1.0 - p_veto) * (1.0 - P_CRITIC_VETO)
        # Debate/MoA already paid extra_roles; still only veto, no p lift here.
        if p_veto and rng.random() < p_veto:
            veto = True
    if veto:
        a.veto = 1
        a.after_saved = 1
        if hier_state is not None and opt.hier:
            thompson_update(hier_state, hier_state.get("_last_policy", "live"), 0)
        return a

    # Honest gate: after-edit suite must run for a keep (and for a graded fail).
    a.after_gates = 1
    a.secs += ta
    if would_keep:
        a.kept = 1
        if planted:
            a.planted_kept = 1
        else:
            a.real_kept = 1
    if hier_state is not None and opt.hier:
        thompson_update(hier_state, hier_state.get("_last_policy", "live"), a.kept)
    return a


# ---------------------------------------------------------------------------
# Horizons: iid (infinite mix) and finite pool + wall clock
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    kept: int = 0
    real_kept: int = 0
    planted_kept: int = 0
    attempts: int = 0
    planted_attempts: int = 0
    secs: float = 0.0
    idle_s: float = 0.0
    model_calls: int = 0
    after_gates: int = 0
    after_saved: int = 0
    false_reject: int = 0
    no_edit: int = 0
    dry: bool = False


def _accumulate(out: RunResult, a: Attempt) -> None:
    out.kept += a.kept
    out.real_kept += a.real_kept
    out.planted_kept += a.planted_kept
    out.attempts += 1
    out.planted_attempts += a.planted
    out.secs += a.secs
    out.model_calls += a.model_calls
    out.after_gates += a.after_gates
    out.after_saved += a.after_saved
    out.false_reject += a.false_reject
    out.no_edit += a.no_edit


def run_iid(opt: Option, scen: Scenario, T: int, rng: random.Random) -> RunResult:
    out = RunResult()
    hier: Dict[str, Any] = {}
    for _ in range(T):
        planted = opt.planted_mix > 0.0 and rng.random() < opt.planted_mix
        _accumulate(out, run_attempt(opt, scen, rng, planted=planted, hier_state=hier if opt.hier else None))
    return out


@dataclass
class Goal:
    via: str
    tries: int
    easy: bool
    p_s: float


def make_pool(n: int, scen: Scenario, loc: bool, rng: random.Random) -> List[Goal]:
    pool: List[Goal] = []
    # Allocate by live shares, rounding so the total is exactly n.
    raw = {v: n * LIVE_SHARE[v] for v in VIA_NAMES}
    counts = {v: int(math.floor(raw[v])) for v in VIA_NAMES}
    # Largest remainder
    rem = n - sum(counts.values())
    order = sorted(VIA_NAMES, key=lambda v: raw[v] - counts[v], reverse=True)
    for i in range(rem):
        counts[order[i % len(order)]] += 1
    for v, c in counts.items():
        easy_frac, p_s = scen.easy_frac(v, loc=loc)
        for _ in range(c):
            easy = rng.random() < easy_frac
            pool.append(Goal(via=v, tries=MAX_TRIES, easy=easy, p_s=(p_s if easy else 0.0)))
    rng.shuffle(pool)
    return pool


def selectable(pool: List[Goal], flow: bool, rng: random.Random) -> Optional[int]:
    idxs = [i for i, g in enumerate(pool) if g.tries > 0]
    if not idxs:
        return None
    if not flow:
        return idxs[rng.randrange(len(idxs))]
    # Prefer test_import, then lint, then others.
    for pref in ("test_import", "lint", "test_import_assign", "import_error", "sbfl"):
        hit = [i for i in idxs if pool[i].via == pref]
        if hit:
            return hit[rng.randrange(len(hit))]
    return idxs[rng.randrange(len(idxs))]


def run_pool(opt: Option, scen: Scenario, wall_s: float, rng: random.Random,
             n_goals: int = LIVE_OPEN) -> RunResult:
    """Finite pool of n_goals × MAX_TRIES. Idle once dry unless refill is on."""
    out = RunResult()
    hier: Dict[str, Any] = {}
    pool = make_pool(n_goals, scen, loc=opt.loc, rng=rng)
    t = 0.0
    # Hard cap so a refill policy cannot spin forever in a test with a huge wall.
    steps = 0
    max_steps = 10_000
    while t < wall_s and steps < max_steps:
        steps += 1
        # Optional planted mix while the real pool still has tries.
        idx = selectable(pool, opt.flow, rng)
        use_planted = False
        if idx is not None and opt.planted_mix > 0.0 and rng.random() < opt.planted_mix:
            use_planted = True
        elif idx is None:
            if opt.refill:
                use_planted = True
            else:
                out.idle_s += wall_s - t
                out.dry = True
                break
        if use_planted:
            a = run_attempt(opt, scen, rng, planted=True, hier_state=hier if opt.hier else None)
            # generation / validation of a planted mutant: one baseline-sized test run, CPU+pytest, counted
            a.secs += scen.t_base
            t += a.secs
            if t > wall_s:
                # still count the attempt that started before the cap
                pass
            _accumulate(out, a)
            continue
        assert idx is not None
        g = pool[idx]
        a = run_attempt(opt, scen, rng, via=g.via, planted=False,
                        hier_state=hier if opt.hier else None,
                        solvable=g.easy, p_each=g.p_s)
        g.tries -= 1
        if a.real_kept:
            g.tries = 0  # a keep resolves the goal (and, in the host, siblings)
        t += a.secs
        _accumulate(out, a)
    if t >= wall_s and selectable(pool, False, rng) is None and not opt.refill:
        out.dry = True
    return out


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def summarise(rows: List[RunResult], mode: str) -> Dict[str, Any]:
    def col(fn) -> List[float]:
        return [float(fn(r)) for r in rows]

    attempts = col(lambda r: r.attempts)
    secs = col(lambda r: r.secs)
    kept = col(lambda r: r.kept)
    real = col(lambda r: r.real_kept)
    kpa = [r.kept / r.attempts if r.attempts else 0.0 for r in rows]
    rkpa = [r.real_kept / max(1, r.attempts - r.planted_attempts) if (r.attempts - r.planted_attempts) else 0.0 for r in rows]
    # GPU-hour uses active attempt seconds only (idle is not GPU).
    kgpu = [(r.kept / r.secs) * 3600.0 if r.secs else 0.0 for r in rows]
    rkgpu = [(r.real_kept / r.secs) * 3600.0 if r.secs else 0.0 for r in rows]
    return {
        "n_seeds": len(rows),
        "mode": mode,
        "attempts": round(_mean(attempts), 2),
        "attempts_std": round(_std(attempts), 2),
        "kept": round(_mean(kept), 3),
        "real_kept": round(_mean(real), 3),
        "planted_kept": round(_mean(col(lambda r: r.planted_kept)), 3),
        "kept_per_attempt": round(_mean(kpa), 4),
        "kept_per_attempt_std": round(_std(kpa), 4),
        "real_kept_per_attempt": round(_mean(rkpa), 4),
        "kept_per_gpu_hour": round(_mean(kgpu), 3),
        "kept_per_gpu_hour_std": round(_std(kgpu), 3),
        "real_kept_per_gpu_hour": round(_mean(rkgpu), 3),
        "secs": round(_mean(secs), 1),
        "idle_s": round(_mean(col(lambda r: r.idle_s)), 1),
        "dry_share": round(sum(1 for r in rows if r.dry) / len(rows), 3) if rows else 0.0,
        "model_calls_per_attempt": round(_mean([r.model_calls / r.attempts if r.attempts else 0 for r in rows]), 3),
        "after_gates_per_attempt": round(_mean([r.after_gates / r.attempts if r.attempts else 0 for r in rows]), 3),
        "after_saved_per_attempt": round(_mean([r.after_saved / r.attempts if r.attempts else 0 for r in rows]), 3),
        "false_reject_per_attempt": round(_mean([r.false_reject / r.attempts if r.attempts else 0 for r in rows]), 4),
        "no_edit_share": round(_mean([r.no_edit / r.attempts if r.attempts else 0 for r in rows]), 4),
        "planted_share": round(_mean([r.planted_attempts / r.attempts if r.attempts else 0 for r in rows]), 4),
        "filler_rate": 0.0,
    }


def analytic_baseline_cost(p_no_edit: float = P_NO_EDIT, t_base: float = T_BASE,
                           t_model: float = T_MODEL, t_after: float = T_AFTER) -> float:
    """Expected seconds of a post-batch-10 solo attempt (no timeout aborts)."""
    return t_base + t_model + (1.0 - p_no_edit) * t_after


def analytic_live_identity() -> Dict[str, float]:
    return {
        "p_keep": LIVE_REAL_PASSES / LIVE_REAL_GRADED,
        "secs_per_attempt": LIVE_SECS_PER_ATTEMPT,
        "kept_per_gpu_hour": LIVE_REAL_PASSES / LIVE_GPU_HOURS,
        "kept_per_gpu_hour_rounded": LIVE_KEPT_PER_GPU_HOUR,
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_suite(seeds: int, horizons: List[int], wall_s: float,
              seed0: int = 20261126) -> Dict[str, Any]:
    scenarios = build_scenarios()
    out: Dict[str, Any] = {
        "label": "SIMULATION — live-calibrated assumptions, not a 1650 swarm measurement",
        "live": {
            "generated": LIVE_GENERATED,
            "real_graded": LIVE_REAL_GRADED,
            "real_passes": LIVE_REAL_PASSES,
            "gpu_hours": LIVE_GPU_HOURS,
            "kept_per_attempt": round(LIVE_REAL_PASSES / LIVE_REAL_GRADED, 4),
            "kept_per_gpu_hour": LIVE_KEPT_PER_GPU_HOUR,
            "secs_per_attempt": round(LIVE_SECS_PER_ATTEMPT, 2),
            "dup_share": LIVE_DUP_SHARE,
            "revert_rate": LIVE_REVERT_RATE,
            "regressions_reverted": LIVE_REGRESSIONS,
            "filler_rate_all_kept_including_legacy": LIVE_FILLER_RATE,
            "filler_note": "0.9556 is the share of *all* kept rows (including 43 legacy) whose goal id is filler; the 2 real keeps are not filler. Do not read this as a real-goal filler rate.",
            "by_via": {v: {"attempts": VIA_N[v], "kept": VIA_KEEP[v]} for v in VIA_NAMES},
            "open_goals": LIVE_OPEN,
            "dry_s": LIVE_DRY_S,
            "identity": analytic_live_identity(),
        },
        "cost_model": {
            "T_BASE": T_BASE,
            "T_MODEL": T_MODEL,
            "T_AFTER": T_AFTER,
            "T_PRE": T_PRE,
            "P_NO_EDIT": P_NO_EDIT,
            "expected_solo_secs": analytic_baseline_cost(),
            "fit": "T_BASE+T_MODEL+T_AFTER = 245 s matches live regression attempts (245–272 s). T_BASE+T_MODEL = 190 s is in the no_function range (180–230 s).",
        },
        "assumptions": {
            "P_PRE_VETO": P_PRE_VETO,
            "P_PRE_KILL": P_PRE_KILL,
            "P_CRITIC_VETO": P_CRITIC_VETO,
            "P_CRITIC_KILL": P_CRITIC_KILL,
            "LOC_FRAC_default": LOC_FRAC,
            "P_PLANTED": P_PLANTED,
            "DUP_TEMP": DUP_TEMP,
            "FLOW_SHARE": FLOW_SHARE,
            "MAX_TRIES": MAX_TRIES,
        },
        "seeds": seeds,
        "horizons": horizons,
        "pool_wall_s": wall_s,
        "scenarios": {},
        "elapsed_s": 0.0,
    }
    t0 = time.time()
    for si, (sname, scen) in enumerate(scenarios.items()):
        block: Dict[str, Any] = {"note": scen.note, "rates": scen.rates, "loc_frac": scen.loc_frac,
                                 "t_base": scen.t_base, "t_model": scen.t_model, "t_after": scen.t_after,
                                 "dup": scen.dup, "sparse": scen.sparse, "iid": {}, "pool": {}}
        for T in horizons:
            iid_block: Dict[str, Any] = {}
            for oi, opt in enumerate(OPTIONS):
                rows = []
                for s in range(seeds):
                    rng = random.Random(seed0 + 1_000_003 * (s + 1) + 10_007 * T + 101 * oi + 13 * si)
                    rows.append(run_iid(opt, scen, T, rng))
                iid_block[opt.name] = summarise(rows, "iid")
                iid_block[opt.name]["title"] = opt.title
            block["iid"][str(T)] = iid_block
        pool_block: Dict[str, Any] = {}
        for oi, opt in enumerate(OPTIONS):
            rows = []
            for s in range(seeds):
                rng = random.Random(seed0 + 7_000_019 * (s + 1) + 101 * oi + 17 * si + 99)
                rows.append(run_pool(opt, scen, wall_s, rng))
            pool_block[opt.name] = summarise(rows, "pool")
            pool_block[opt.name]["title"] = opt.title
        block["pool"] = pool_block
        out["scenarios"][sname] = block
        print(f"{sname} done", flush=True)
    out["elapsed_s"] = round(time.time() - t0, 2)
    # Compact ranking on the default scenario / T=238 iid, plus pool dry time.
    out["ranking"] = ranking_tables(out)
    return out


def ranking_tables(out: Dict[str, Any]) -> Dict[str, Any]:
    """Pull a readable table for the design doc from the default scenario."""
    default = "homogeneous"
    iid_h = out["scenarios"][default]["iid"]
    t = "238" if "238" in iid_h else sorted(iid_h, key=int)[0]
    iid = iid_h[t]
    pool = out["scenarios"][default]["pool"]
    rows = []
    for opt in OPTIONS:
        i = iid[opt.name]
        p = pool[opt.name]
        rows.append({
            "option": opt.name,
            "title": opt.title,
            "fit": _fit_label(opt.name),
            "model_calls": i["model_calls_per_attempt"],
            "kept_per_attempt": i["kept_per_attempt"],
            "kept_per_gpu_hour": i["kept_per_gpu_hour"],
            "real_kept_per_attempt": i["real_kept_per_attempt"],
            "real_kept_per_gpu_hour": i["real_kept_per_gpu_hour"],
            "after_saved_per_attempt": i["after_saved_per_attempt"],
            "filler": i["filler_rate"],
            "pool_idle_s": p["idle_s"],
            "pool_dry_share": p["dry_share"],
            "pool_real_kept": p["real_kept"],
            "verdict": _verdict(opt.name),
        })
    return {"scenario": default, "iid_horizon": 238, "pool_wall_s": out["pool_wall_s"], "rows": rows}


def _fit_label(name: str) -> str:
    return {
        "baseline": "reference",
        "zero_model": "best fit",
        "hier_bag": "poor at n=2 keeps",
        "critic_4b": "weak fit (false-reject risk)",
        "critic_det": "good fit (subset of #1)",
        "bon2": "good fit once the queue flows",
        "bon4": "ok fit, heavier",
        "planted": "good fit when dry",
        "goal_flow": "best fit for the outage",
        "zero_plus_flow": "best overall",
        "zero_flow_bon2": "best follow-on",
        "debate": "reject",
        "moa": "reject",
        "evo_prompt": "reject",
    }[name]


def _verdict(name: str) -> str:
    return {
        "baseline": "post-batch-10 reference; still starves once the 95-goal pool is exhausted",
        "zero_model": "ship flag-gated: no extra 4B call, can only reject or add context",
        "hier_bag": "iid lift is prefer-import (a scout rule); in a finite pool it can exhaust the solvable slice first. Hard-code interleaving in #6, do not add prompt arms",
        "critic_4b": "do not ship; 4B false-reject of a rare keep is too expensive",
        "critic_det": "ship as part of #1, not a separate role",
        "bon2": "second flag after #1+#6; cheap because T_MODEL << T_BASE",
        "bon4": "hold until BoN=2 is measured; +90 s per attempt",
        "planted": "turn on when selectable=0 (already built, ETHER_PLANTED_GOALS)",
        "goal_flow": "ship with #1; this is what ends the empty-queue outage",
        "zero_plus_flow": "recommended next-batch default behind ETHER_SWARM=gems",
        "zero_flow_bon2": "recommended second flag ETHER_BEST_OF=2",
        "debate": "reject: 3× model calls, no coverage gain, judge can kill a keep",
        "moa": "reject: 5× model calls, aggregator can drop a good candidate",
        "evo_prompt": "reject: 8 arms dilutes 2 keeps; ETHER_NEURO_ES already exists and must not self-promote",
    }[name]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--horizons", default="238,1000")
    ap.add_argument("--wall-s", type=float, default=48 * 3600.0,
                    help="finite-pool wall-clock horizon in seconds (default 48 h)")
    ap.add_argument("--out", default=str(ROOT / "docs/results/swarm/swarm_sim.json"))
    args = ap.parse_args()
    horizons = [int(x) for x in args.horizons.split(",") if x.strip()]
    out = run_suite(args.seeds, horizons, args.wall_s)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} in {out['elapsed_s']}s")
    # Print the default ranking table for the commit message / doc author.
    print("option                     k/att   k/gpu-h  real-k/att  after_saved  pool_idle_h  verdict")
    for r in out["ranking"]["rows"]:
        print(f"{r['option']:24} {r['kept_per_attempt']:7.4f} {r['kept_per_gpu_hour']:8.3f} "
              f"{r['real_kept_per_attempt']:10.4f} {r['after_saved_per_attempt']:11.3f} "
              f"{r['pool_idle_s']/3600:11.2f}  {r['verdict'][:40]}")


if __name__ == "__main__":
    main()
