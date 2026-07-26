#!/usr/bin/env python3
"""Side-by-side log skeleton for ETHER vs external tools (manual fill for others)."""

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
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    tasks = json.loads(HOLDOUT.read_text(encoding="utf-8")).get("tasks") or []
    tasks = tasks[: args.limit]
    pipe = Pipeline()
    rows = []
    t0 = time.perf_counter()
    for t in tasks:
        tid = t.get("id")
        print(f"ETHER {tid}...", flush=True)
        st = time.perf_counter()
        r = pipe.run(t["objective"])
        ms = (time.perf_counter() - st) * 1000
        ok = r.status == "complete" and r.sandbox and r.sandbox.exit_code == 0
        rows.append(
            {
                "id": tid,
                "ETHER": "pass" if ok else "fail",
                "ETHER_ms": round(ms, 1),
                "ETHER_conf": r.confidence,
                "Aider": "",  # fill manually
                "Continue": "",
                "Cursor": "",
                "notes": "",
            }
        )
        print(f"  {'PASS' if ok else 'FAIL'} {ms:.0f}ms", flush=True)

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = ROOT / "memory" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"compare_{day}.md"
    lines = [
        f"# Side-by-side compare {day}",
        "",
        "Protocol: METHODOLOGY.md — ETHER column auto; other tools filled by human.",
        "",
        "| Task | ETHER | ms | conf | Aider | Continue | Cursor | notes |",
        "|------|-------|---:|-----:|-------|----------|--------|-------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['ETHER']} | {r['ETHER_ms']} | {r['ETHER_conf']:.2f} |  |  |  |  |"
        )
    lines.append("")
    lines.append(f"_Generated in {time.perf_counter()-t0:.1f}s_")
    path.write_text("\n".join(lines), encoding="utf-8")
    (out_dir / f"compare_{day}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
