#!/usr/bin/env python3
"""Held-out quiz — external-ish judge, never used as flywheel curriculum objectives.

The dataset behind this script (memory/quizzes/holdout_v1.json) used to carry
objectives like:

    Write only Python: def fib(n):
        a,b=0,1
        for _ in range(n):
            a,b=b,a+b
        return a
    assert fib(10)==55

i.e. the answer and the assertion it would be graded on, handed to the model —
and `ok` was `status == "complete" and exit_code == 0`. "Held out" described
where the file lived, not what the model was shown. `pass_rate` read 1.000 and
fed `core/health_metric.py`.

Now each task states a signature plus a behaviour description, and the
assertions live in `holdout_test`, appended after generation by
`core.holdout.grade_against_holdout` (which strips the model's own top-level
asserts and requires an unpredictable sentinel on stdout, so a clean exit
cannot fake a pass). The holdout verdict IS the pass criterion.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv
from core.pipeline import Pipeline
from core.health_metric import compute_health
from core.scoreboard import write_scoreboard

# One auditor and one grading adapter for every harness in scripts/, both
# ultimately backed by core.holdout. Divergent local copies are how
# scripts/hidden_quiz.py ended up grading on a bare exit code.
from scripts.bench import audit_tasks, grade_run, run_task

load_dotenv(ROOT / ".env")

HOLDOUT = ROOT / "memory" / "quizzes" / "holdout_v1.json"


def load_tasks(limit: int = 0, path: Path = HOLDOUT) -> List[Dict[str, Any]]:
    """Quiz tasks in canonical form: id / title / objective / holdout_test.

    Anything auditing this quiz must come through here rather than reading the
    JSON: the loader is where alternate key names are reconciled and where any
    future splice of extra tasks would land. (The equivalent curriculum test
    read tiers.json directly and stayed blind to the tasks `load_tiers()` adds
    at runtime.)
    """
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks: List[Dict[str, Any]] = []
    for t in data.get("tasks") or []:
        tasks.append(
            {
                "id": t.get("id") or "",
                "title": t.get("title") or t.get("id") or "",
                # `prompt` / `hidden_test` are the sibling datasets' key names;
                # accepted so a merged file cannot silently lose its holdout.
                "objective": t.get("objective") or t.get("prompt") or "",
                "holdout_test": t.get("holdout_test") or t.get("hidden_test") or "",
            }
        )
    return tasks[:limit] if limit and limit > 0 else tasks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    tasks = load_tasks(limit=args.limit)
    if not tasks:
        print(f"no quiz tasks in {HOLDOUT}", file=sys.stderr)
        return 2

    # Point-of-use enforcement, as in core/curriculum.py::sample_objective.
    # NOTE: scripts/expand_holdout.py still appends 30 answer-leaking tasks
    # (h21-h50) to this file, so this guard is load-bearing, not decorative.
    leaks = audit_tasks(tasks)
    if leaks:
        print("REFUSING TO RUN — quiz tasks leak their own answers:", file=sys.stderr)
        for problem in leaks:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    pipe = Pipeline()
    results = []
    t0 = time.perf_counter()
    for i, t in enumerate(tasks, 1):
        obj = t["objective"]
        holdout = t["holdout_test"]
        print(f"[quiz {i}/{len(tasks)}] {t.get('id')} ...", flush=True)
        r = run_task(pipe, obj, holdout)
        graded = grade_run(r, holdout)
        results.append(
            {
                "id": t.get("id"),
                # `ok` is the holdout verdict now. It used to be "the process
                # exited 0", which a transcription task cannot fail.
                "ok": graded["ok"],
                "holdout_detail": graded["detail"],
                "status": r.status,
                "confidence": r.confidence,
                "verification_score": r.verification_score,
                "exit_code": r.sandbox.exit_code if r.sandbox else None,
                "total_tests": r.sandbox.total_tests if r.sandbox else 0,
            }
        )
        print(
            f"  ok={graded['ok']} conf={r.confidence:.3f} ver={r.verification_score:.3f}"
            + (f" — {graded['detail']}" if not graded["ok"] and graded["detail"] else ""),
            flush=True,
        )

    passed = sum(1 for x in results if x["ok"])
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "holdout_quiz",
        "n": len(tasks),
        "pass": passed,
        "pass_rate": round(passed / max(1, len(tasks)), 3),
        "graded_on": "holdout",
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
    print(
        json.dumps(
            {
                "pass_rate": summary["pass_rate"],
                "pass": passed,
                "n": len(tasks),
                "graded_on": "holdout",
            },
            indent=2,
        )
    )
    return 0 if passed == len(tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
