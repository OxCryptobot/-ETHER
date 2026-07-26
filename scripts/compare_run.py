#!/usr/bin/env python3
"""Side-by-side log scaffold — records @ETHER results for a fixed holdout slice.

Fill Aider/Continue columns manually per METHODOLOGY.md protocol.
"""

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

HOLDOUT = ROOT / "memory" / "quizzes" / "holdout_v1.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    tasks = json.loads(HOLDOUT.read_text(encoding="utf-8")).get("tasks") or []
    tasks = tasks[: args.limit]
    pipe = Pipeline()
    rows = []
    t0 = time.perf_counter()
    for i, t in enumerate(tasks, 1):
        tid = t.get("id")
        print(f"[{i}/{len(tasks)}] {tid}", flush=True)
        r = pipe.run(t["objective"])
        ok = r.status == "complete" and r.sandbox and r.sandbox.exit_code == 0
        ms = sum(s.duration_ms for s in r.stages)
        rows.append(
            {
                "id": tid,
                "ether_ok": ok,
                "ether_ms": round(ms, 1),
                "ether_conf": r.confidence,
                "ether_burst": r.used_burst,
                "aider_ok": None,
                "continue_ok": None,
                "cursor_ok": None,
                "notes": "",
            }
        )
        print(f"  ether_ok={ok} ms={ms:.0f}", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = ROOT / "memory" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"compare_{stamp}.json"
    md = out_dir / f"compare_{stamp}.md"
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n": len(rows),
        "duration_s": round(time.perf_counter() - t0, 2),
        "rows": rows,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        f"# Compare {stamp}",
        "",
        "| id | ETHER | ms | conf | burst | Aider | Continue | Cursor | notes |",
        "|----|-------|---:|-----:|-------|-------|----------|--------|-------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['ether_ok']} | {r['ether_ms']} | {r['ether_conf']} | {r['ether_burst']} |  |  |  |  |"
        )
    lines.append("")
    lines.append("_Fill other tools manually. Do not claim winners without complete columns._")
    md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"path": str(path), "md": str(md), "n": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
