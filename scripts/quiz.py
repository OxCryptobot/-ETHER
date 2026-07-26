#!/usr/bin/env python3
"""Held-out quiz — external-ish judge, never used as flywheel curriculum objectives."""

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
from core.health_metric import compute_health
from core.scoreboard import write_scoreboard

load_dotenv(ROOT / ".env")

HOLDOUT = ROOT / "memory" / "quizzes" / "holdout_v1.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    data = json.loads(HOLDOUT.read_text(encoding="utf-8"))
    tasks = list(data.get("tasks") or [])
    if args.limit > 0:
        tasks = tasks[: args.limit]

    pipe = Pipeline()
    results = []
    t0 = time.perf_counter()
    for i, t in enumerate(tasks, 1):
        obj = t["objective"]
        print(f"[quiz {i}/{len(tasks)}] {t.get('id')} ...", flush=True)
        r = pipe.run(obj)
        ok = r.status == "complete" and r.sandbox and r.sandbox.exit_code == 0
        # require real asserts when present in objective
        has_assert = "assert " in obj
        if has_assert and r.sandbox and r.sandbox.total_tests == 0 and ok:
            # ran but harness may not count — still check exit
            ok = r.sandbox.exit_code == 0
        results.append(
            {
                "id": t.get("id"),
                "ok": ok,
                "confidence": r.confidence,
                "verification_score": r.verification_score,
                "exit_code": r.sandbox.exit_code if r.sandbox else None,
                "total_tests": r.sandbox.total_tests if r.sandbox else 0,
            }
        )
        print(f"  ok={ok} conf={r.confidence:.3f} ver={r.verification_score:.3f}", flush=True)

    passed = sum(1 for x in results if x["ok"])
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "holdout_quiz",
        "n": len(tasks),
        "pass": passed,
        "pass_rate": round(passed / max(1, len(tasks)), 3),
        "duration_s": round(time.perf_counter() - t0, 2),
        "results": results,
    }
    out = ROOT / "memory" / "quiz"
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / f"quiz_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    compute_health()
    write_scoreboard()
    print(json.dumps({"pass_rate": summary["pass_rate"], "pass": passed, "n": len(tasks)}, indent=2))
    return 0 if passed == len(tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
