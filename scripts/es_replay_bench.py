"""Offline bench: (1+lambda)-ES vs the existing bandit on replayed trajectories.

CPU only, no model, no network. Writes only to the --out path (default out/).
Part A is SYNTHETIC (known pass probabilities) so true policy value is exact.
Part B replays the repo's real non-scripted scoreboard rows (tiny, no logged
propensities; uniform logging is ASSUMED) and is descriptive only.
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import core.learning as learning  # noqa: E402
from core.agent import evolve_es, outcome  # noqa: E402

BUCKET_CTX = {
    "gen|simple": {"tier": 0, "fail_kind": "", "multifile": False},
    "repair_syntax|simple": {"tier": 0, "fail_kind": "SyntaxError", "multifile": False},
    "repair_logic|simple": {"tier": 0, "fail_kind": "tests_failed", "multifile": False},
}


def true_value(policy, truth):
    return sum(sum(p * truth[b][a] for a, p in policy[b].items()) for b in truth) / len(truth)


def greedy(pol, buckets):
    out = {}
    for b in buckets:
        scores = {a: pol.score(b, a) for a in pol.arms}
        top = max(scores, key=scores.get)
        out[b] = {a: (1.0 if a == top else 0.0) for a in pol.arms}
    return out


def one_seed(seed: int, steps: int, tmp: Path):
    rng = random.Random(seed)
    random.seed(seed)
    truth = {b: {a: rng.betavariate(1.0, 3.0) for a in learning.STRATEGIES} for b in BUCKET_CTX}
    root = tmp / f"s{seed}_{steps}"
    pol = learning.BanditPolicy(path=root / "bandit.json")
    data = []
    for _ in range(steps):
        b = rng.choice(list(BUCKET_CTX))
        ctx = BUCKET_CTX[b]
        arm = pol.select(ctx)
        prop = outcome.propensity_of(pol, b, arm, str(pol.last_decision.get("reason")))
        ok = rng.random() < truth[b][arm]
        kind = "pass" if ok else "fail"
        data.append((b, arm, prop, 1.0 if ok else 0.0))
        pol.update(arm, outcome.reward_for(kind), context=ctx)
    buckets = list(BUCKET_CTX)
    bandit_eps = evolve_es.bandit_policy(pol, buckets)
    bandit_greedy = greedy(pol, buckets)
    t0 = time.perf_counter()
    fit_data, hold = evolve_es.split(data, seed=seed)
    genome, _ = evolve_es.evolve(evolve_es.from_bandit(pol, buckets), fit_data, rng=random.Random(seed + 1))
    es_ms = (time.perf_counter() - t0) * 1000
    es = evolve_es.phenotype(genome)
    es_val, es_ess = evolve_es.snips(es, hold)
    b_val, _ = evolve_es.snips(bandit_eps, hold)
    accepted = es_ess >= evolve_es.MIN_ESS and es_val >= b_val + evolve_es.MARGIN
    oracle = sum(max(v.values()) for v in truth.values()) / len(truth)
    return {
        "bandit_eps": true_value(bandit_eps, truth),
        "bandit_greedy": true_value(bandit_greedy, truth),
        "es": true_value(es, truth),
        "oracle": oracle,
        "accepted": accepted,
        "es_ms": es_ms,
    }


def part_a(seeds: int, steps_list, tmp: Path):
    out = {}
    for steps in steps_list:
        rows = [one_seed(s, steps, tmp) for s in range(seeds)]
        acc = [r for r in rows if r["accepted"]]
        mean = lambda k, rs=rows: round(sum(r[k] for r in rs) / len(rs), 4) if rs else None  # noqa: E731
        out[str(steps)] = {
            "seeds": seeds,
            "true_pass_rate": {k: mean(k) for k in ("bandit_eps", "bandit_greedy", "es", "oracle")},
            "es_beats_bandit_eps_seeds": sum(1 for r in rows if r["es"] > r["bandit_eps"]),
            "es_beats_bandit_greedy_seeds": sum(1 for r in rows if r["es"] > r["bandit_greedy"]),
            "gate_accepted": len(acc),
            "gate_precision_vs_eps": (round(sum(1 for r in acc if r["es"] > r["bandit_eps"]) / len(acc), 3) if acc else None),
            "deployed_value_with_gate": round(sum((r["es"] if r["accepted"] else r["bandit_eps"]) for r in rows) / len(rows), 4),
            "es_fit_ms_mean": round(sum(r["es_ms"] for r in rows) / len(rows), 1),
        }
    return out


def part_b():
    rows = []
    for f in sorted(glob.glob(str(ROOT / "artifacts" / "**" / "scoreboard*.json"), recursive=True)):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        items = d if isinstance(d, list) else (d.get("rows") or d.get("results") or d.get("episodes") or [])
        for r in items if isinstance(items, list) else []:
            if isinstance(r, dict) and r.get("strategy") and "scripted" not in str(r.get("strategy")):
                rows.append(r)
    arms = sorted({str(r["strategy"]) for r in rows})
    if not rows:
        return {"n": 0}
    prop = 1.0 / len(arms)
    data = [(str(r.get("fixture") or ""), str(r["strategy"]), prop,
             1.0 if (r.get("ok") or (r.get("score") or 0) >= 0.99) else 0.0) for r in rows]
    per_arm = {a: [x[3] for x in data if x[1] == a] for a in arms}
    buckets = sorted({x[0] for x in data})
    uniform = {b: {a: prop for a in arms} for b in buckets}
    genome, _ = evolve_es.evolve({b: {a: 0.0 for a in arms} for b in buckets}, data,
                                 rng=random.Random(0), min_ess=3.0)
    es_val, es_ess = evolve_es.snips(evolve_es.phenotype(genome), data)
    u_val, u_ess = evolve_es.snips(uniform, data)
    return {
        "n": len(data),
        "assumption": "uniform logging propensity; no logged propensities exist in the repo",
        "per_arm": {a: {"n": len(v), "passes": int(sum(v))} for a, v in per_arm.items()},
        "fixtures": buckets,
        "uniform_snips": round(u_val, 4),
        "es_snips": round(es_val, 4),
        "es_ess": round(es_ess, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--steps", default="60,300")
    ap.add_argument("--out", default=str(ROOT / "out" / "es_bench.json"))
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        learning.EXP_PATH = Path(tmp) / "experience.jsonl"
        result = {
            "part_a_synthetic": part_a(args.seeds, [int(x) for x in args.steps.split(",")], Path(tmp)),
            "part_b_real_scoreboards": part_b(),
        }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
