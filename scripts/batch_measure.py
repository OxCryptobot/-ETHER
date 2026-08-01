"""Batch Phase C measurement — scripted parallel then optional live sequential.

  python -m scripts.batch_measure              # scripted hard, parallel
  python -m scripts.batch_measure --live       # scripted then live hard
  python -m scripts.batch_measure --live --tier all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measure_tool_runtime import main as measure_main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["easy", "hard", "all"], default="hard")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=400.0)
    ap.add_argument("--scoreboard", default="artifacts/scoreboard_phasec.json")
    args = ap.parse_args()

    print("=== scripted batch ===", flush=True)
    rc = measure_main([
        "--tier", args.tier,
        "--jobs", str(args.jobs),
        "--timeout", "120",
        "--scoreboard", args.scoreboard.replace(".json", "_scripted.json"),
    ])
    if rc != 0:
        print("scripted failures — abort live", flush=True)
        return rc
    if not args.live:
        return 0
    print("=== live batch (sequential) ===", flush=True)
    return measure_main([
        "--tier", args.tier,
        "--live",
        "--jobs", "1",
        "--timeout", str(args.timeout),
        "--scoreboard", args.scoreboard,
    ])


if __name__ == "__main__":
    raise SystemExit(main())
