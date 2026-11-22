"""Render docs/results/batch8/rl_sim.json as markdown tables (SIMULATION)."""
import json
import sys
from pathlib import Path

d = json.loads((Path(__file__).parent / "rl_sim.json").read_text())
cols = ("kept", "kept_ci95", "kept_at_60_attempts", "attempts", "kept_per_gpu_hour", "dup_share", "first_keep_median", "top_share")
out = []
for exp, v in d["results"].items():
    out.append(f"\n### {exp}\n")
    out.append("| scenario | policy (goal / arm / temperature) | kept (±95%) | kept @60 att. | attempts | kept/GPU-h | dup share | 1st keep (median att.) | top arm share |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for sc, rows in v.items():
        for k, r in rows.items():
            out.append(f"| {sc} | {k} | {r['kept']:.2f} ± {r['kept_ci95']:.2f} | {r['kept_at_60_attempts']:.2f} | {r['attempts']:.0f} | "
                       f"{r['kept_per_gpu_hour']:.2f} | {r['dup_share']:.3f} | {r['first_keep_median']} | {r['top_share']:.2f} |")
text = "\n".join(out) + "\n"
(Path(__file__).parent / "rl_sim.md").write_text("SIMULATION — assumed pass rates, not host data.\n" + text)
print(text)
