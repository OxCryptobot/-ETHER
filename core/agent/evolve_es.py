"""(1+lambda)-ES over the bandit's arm preferences, fit offline on stored trajectories.

No gradients through the model. No GPU. The genome is one logit per (bucket, arm)
for the EXISTING bandit's arms; the phenotype is a softmax exploration policy.

Fitness = self-normalised importance-weighted (SNIPS) honest-gate pass rate on
logged trajectories, using the propensity the bandit logged when it acted.
Candidates with too few effective samples are rejected.

The ES never promotes anything. Behind ETHER_NEURO_ES=1 it only replaces the
epsilon-greedy *exploration* distribution; promotion still goes through
core.agent.outcome.maybe_promote (3 honest-gate passes).
"""
from __future__ import annotations

import math
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

Genome = Dict[str, Dict[str, float]]

MIN_ESS = 8.0
MARGIN = 0.05
L2 = 0.002


def enabled() -> bool:
    return os.getenv("ETHER_NEURO_ES", "0") == "1"


def softmax(logits: Dict[str, float]) -> Dict[str, float]:
    if not logits:
        return {}
    top = max(logits.values())
    exp = {k: math.exp(v - top) for k, v in logits.items()}
    total = sum(exp.values())
    return {k: v / total for k, v in exp.items()}


def _graded(rows: Iterable[Dict[str, Any]]) -> List[Tuple[str, str, float, float]]:
    out = []
    for r in rows:
        if r.get("kind") not in ("pass", "fail"):
            continue
        prop = float(r.get("propensity") or 0.0)
        if prop <= 0.0:
            continue
        out.append((str(r.get("bucket") or ""), str(r.get("arm") or ""), prop,
                    1.0 if r.get("kind") == "pass" and r.get("tests_ok") else 0.0))
    return out


def snips(policy: Dict[str, Dict[str, float]], data: List[Tuple[str, str, float, float]]) -> Tuple[float, float]:
    """(value, effective sample size) of a stochastic policy on logged data."""
    num = den = sq = 0.0
    for bucket, arm, prop, reward in data:
        p = policy.get(bucket, {}).get(arm, 0.0)
        w = p / prop
        num += w * reward
        den += w
        sq += w * w
    if den <= 0.0:
        return 0.0, 0.0
    return num / den, (den * den) / sq if sq > 0 else 0.0


def phenotype(genome: Genome) -> Dict[str, Dict[str, float]]:
    return {b: softmax(arms) for b, arms in genome.items()}


LCB_K = 1.0


def fitness(genome: Genome, data, min_ess: float = MIN_ESS, anchor: Optional[Genome] = None) -> float:
    """Pessimistic: SNIPS value minus LCB_K standard errors at the policy's ESS.
    Plain SNIPS rewarded piling onto arms with a few lucky passes."""
    value, ess = snips(phenotype(genome), data)
    # Stay near the bandit's own preferences (the anchor); an absolute L2 pulled
    # every logit to 0, i.e. toward a uniform policy.
    anchor = anchor or {}
    reg = L2 * sum((v - anchor.get(b, {}).get(a, 0.0)) ** 2 for b, arms in genome.items() for a, v in arms.items())
    if ess < min_ess:
        return value - 1.0 - reg
    se = math.sqrt(max(value * (1.0 - value), 1e-4) / ess)
    return value - LCB_K * se - reg


def split(data: list, frac: float = 0.7, seed: int = 0) -> Tuple[list, list]:
    """Fit on one part, gate on the other. Gating on the fit data accepted
    candidates that were worse than the bandit."""
    idx = list(range(len(data)))
    random.Random(seed).shuffle(idx)
    cut = int(len(idx) * frac)
    return [data[i] for i in idx[:cut]], [data[i] for i in idx[cut:]]


def from_bandit(pol, buckets: Iterable[str], beta: float = 40.0) -> Genome:
    """Seed the genome from the existing bandit's scores (its soft preference)."""
    return {b: {a: beta * pol.score(b, a) for a in pol.arms} for b in buckets}


def bandit_policy(pol, buckets: Iterable[str]) -> Dict[str, Dict[str, float]]:
    """The existing bandit's own action distribution (epsilon-greedy)."""
    out = {}
    for b in buckets:
        arms = list(pol.arms)
        scores = {a: pol.score(b, a) for a in arms}
        top = max(scores.values())
        best = [a for a, s in scores.items() if s >= top - 1e-9]
        eps = pol.effective_epsilon(b)
        n = len(arms)
        dist = {}
        for a in arms:
            p = (1 - eps) / len(best) if a in best else 0.0
            p += eps * sum(1.0 / len(best) for g in best if g != a) / max(1, n - 1)
            dist[a] = p
        out[b] = dist
    return out


def evolve(seed: Genome, data, *, lam: int = 8, sigma: float = 0.5, gens: int = 60,
           rng: Optional[random.Random] = None, min_ess: float = MIN_ESS) -> Tuple[Genome, float]:
    """(1+lambda)-ES with the 1/5th success rule."""
    rng = rng or random.Random(0)
    parent = {b: dict(arms) for b, arms in seed.items()}
    best = fitness(parent, data, min_ess, seed)
    for _ in range(gens):
        wins = 0
        champ, champ_fit = None, best
        for _ in range(lam):
            child = {b: {a: v + sigma * rng.gauss(0.0, 1.0) for a, v in arms.items()} for b, arms in parent.items()}
            f = fitness(child, data, min_ess, seed)
            if f > best:
                wins += 1
            if f > champ_fit:
                champ, champ_fit = child, f
        if champ is not None:
            parent, best = champ, champ_fit
        sigma *= 1.22 if wins / lam > 0.2 else 0.82
        sigma = max(0.02, min(2.0, sigma))
    return parent, best


def propose(root: Path, rng: Optional[random.Random] = None) -> Dict[str, Any]:
    """Fit a candidate on the stored trajectories. Accept only if it beats the
    bandit's own policy offline by MARGIN with enough effective samples."""
    from core.agent.outcome import policy, trajectories
    from core.spine.state_io import write_json

    data = _graded(trajectories(root))
    pol = policy(root)
    buckets = sorted({b for b, _, _, _ in data}) or ["gen|simple"]
    fit_data, hold = split(data)
    genome, _ = evolve(from_bandit(pol, buckets), fit_data, rng=rng)
    base_value, base_ess = snips(bandit_policy(pol, buckets), hold)
    value, ess = snips(phenotype(genome), hold)
    accepted = bool(hold) and ess >= MIN_ESS and value >= base_value + MARGIN
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n": len(data),
        "n_holdout": len(hold),
        "bandit_value": round(base_value, 4),
        "bandit_ess": round(base_ess, 2),
        "es_value": round(value, 4),
        "es_ess": round(ess, 2),
        "accepted": accepted,
        "policy": {b: {a: round(p, 4) for a, p in d.items()} for b, d in phenotype(genome).items()},
    }
    write_json(Path(root) / "memory" / "learning" / "es_candidate.json", row)
    return row


def candidate(root: Path) -> Dict[str, Any]:
    from core.spine.state_io import read_json

    data = read_json(Path(root) / "memory" / "learning" / "es_candidate.json", {})
    return data if isinstance(data, dict) else {}


def sample(root: Path, bucket: str, rng: Optional[random.Random] = None) -> Optional[Tuple[str, float]]:
    """Draw an exploration arm from an accepted candidate. None if no candidate."""
    row = candidate(root)
    if not row.get("accepted"):
        return None
    dist = (row.get("policy") or {}).get(bucket)
    if not dist:
        return None
    rng = rng or random
    x, acc = rng.random(), 0.0
    for arm, p in dist.items():
        acc += float(p)
        if x <= acc:
            return arm, max(1e-6, float(p))
    arm, p = list(dist.items())[-1]
    return arm, max(1e-6, float(p))
