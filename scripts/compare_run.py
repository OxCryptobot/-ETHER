#!/usr/bin/env python3
"""Side-by-side log runner — records @ETHER results on holdout sample for comparison tables."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv
from core.pipeline import Pipeline

load_dotenv(ROOT / ".env")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    holdout = json.loads((ROOT / "memory" / "quizzes" / "holdout_v1.json").read_text(encoding="utf-8"))
    tasks = list(holdout.get("tasks") or [])[: args.limit]
    pipe = Pipeline()
    rows = []
    t0 = time.perf_counter()
    for t in tasks:
        tid = t.get("id")
        print(f"compare {tid} ...", flush=True)
        st = time.perf_counter()
        r = pipe.run(t["objective"])
        ms = round((time.perf_counter() - st) * 1000)
        ok = r.status == "complete" and r.sandbox and r.sandbox.exit_code == 0
        rows.append(
            {
                "id": tid,
                "ether_ok": ok,
                "ether_ms": ms,
                "conf": r.confidence,
                "ver": r.verification_score,
                "strategy": r.strategy,
                "burst": r.used_burst,
                "aider": "",
                "continue": "",
                "cursor": "",
                "notes": "",
            }
        )
        print(f"  ok={ok} ms={ms}", flush=True)

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = ROOT / "memory" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"compare_{day}.json"
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(time.perf_counter() - t0, 2),
        "n": len(rows),
        "ether_pass": sum(1 for x in rows if x["ether_ok"]),
        "rows": rows,
        "instructions": (
            "Fill aider/continue/cursor columns manually after running the same task ids "
            "in those tools; do not claim winners without a complete table."
        ),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # markdown table stub
    md = ["# Comparison " + day, "", "| id | ETHER | ms | Aider | Continue | Cursor | notes |", "|----|-------|----|-------|----------|--------|-------|"]
    for x in rows:
        md.append(
            f"| {x['id']} | {'OK' if x['ether_ok'] else 'FAIL'} | {x['ether_ms']} |  |  |  |  |"
        )
    md_path = out_dir / f"compare_{day}.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(path), "md": str(md_path), "ether_pass": payload["ether_pass"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
