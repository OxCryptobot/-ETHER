"""Render docs/results/batch4/bandit_sim.json as markdown tables (used in docs/BANDITS.md)."""
import json
import sys

d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "docs/results/batch4/bandit_sim.json"))
for sc, hs in d["results"].items():
    for h, algos in sorted(hs.items(), key=lambda kv: int(kv[0])):
        print(f"\n**{sc}, T={h}** ({d['seeds']} seeds)\n")
        print("| selector | regret (±95%) | p90 regret | kept/attempt | kept/GPU-h | locked on wrong arm | promote (posterior): correct by T / median t / wrong per run | promote (batch-2 score rule): correct / median t / wrong |")
        print("|---|---|---|---|---|---|---|---|")
        for a, r in algos.items():
            pp, ps = r["promote_posterior"], r["promote_score"]
            print(f"| {a} | {r['regret']:.1f} ±{r['regret_ci95']:.1f} | {r['regret_p90']:.1f} | {r['kept_per_attempt']:.3f} | "
                  f"{r['kept_per_gpu_hour']:.2f} | {r['locked_wrong']:.2f} | {pp['share_correct_by_T']:.2f} / {pp['median_t']} / {pp['wrong_per_run']:.2f} | "
                  f"{ps['share_correct_by_T']:.2f} / {ps['median_t']} / {ps['wrong_per_run']:.2f} |")
