#!/usr/bin/env python3
"""Minimal regression bench for @ETHER pipeline."""

from __future__ import annotations

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

TASKS = [
    "Write only Python: def is_even(n):\n    return n % 2 == 0\nprint(is_even(4))\nprint(is_even(5))",
    "Write only Python: def add(a,b):\n    return a+b\nprint(add(2,3))",
    "Write only Python: def reverse_string(s):\n    return s[::-1]\nprint(reverse_string('abc'))",
]


def main() -> int:
    out_dir = ROOT / "memory" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    pipe = Pipeline()
    t0 = time.perf_counter()
    for i, obj in enumerate(TASKS, 1):
        print(f"[{i}/{len(TASKS)}] running...", flush=True)
        r = pipe.run(obj)
        results.append(
            {
                "i": i,
                "status": r.status,
                "confidence": r.confidence,
                "exit_code": r.sandbox.exit_code if r.sandbox else None,
                "audit": bool(r.audit and r.audit.approved),
                "objective": obj[:80],
            }
        )
        print(
            f"  status={r.status} conf={r.confidence:.3f} exit={results[-1]['exit_code']}",
            flush=True,
        )
    ok = sum(1 for x in results if x["status"] == "complete" and x["exit_code"] == 0)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n": len(TASKS),
        "pass": ok,
        "pass_rate": round(ok / len(TASKS), 3),
        "duration_s": round(time.perf_counter() - t0, 2),
        "results": results,
    }
    path = out_dir / f"bench_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"pass_rate": summary["pass_rate"], "pass": ok, "n": len(TASKS)}, indent=2))
    return 0 if ok == len(TASKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
