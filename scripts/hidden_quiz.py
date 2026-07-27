#!/usr/bin/env python3
"""Hidden-test quiz: model sees the signature only; asserts appended after generation.

This script had the right IDEA and the weaker of two implementations of it. It
built its own `combined = code + hidden_test` string and scored
`ok = exit_code == 0`, which meant:

  * no leak check — a prompt that already contained the hidden asserts still
    graded as a pass;
  * no assertion floor — a hidden_test with nothing observable in it graded
    every submission as a pass;
  * no sentinel — `sys.exit(0)`, `os._exit(0)`, `raise SystemExit(0)` or an
    atexit hook exits 0 before the asserts run, and that scored as a pass;
  * the model's own module-level asserts ran FIRST, so a correct answer
    carrying one bad self-assert was recorded as a hidden-test failure.

`core/holdout.py` exists because of this file (see its module docstring) and
closes all four holes. The output of this script is the scoreboard's
"Hidden HE pass_rate", so the weaker copy was the one being published. It now
calls the shared grader like every other harness.
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

# Shared auditor/grader — see scripts/bench.py. core.holdout does the work.
from scripts.bench import audit_tasks, grade_run, run_task

load_dotenv(ROOT / ".env")

HIDDEN = ROOT / "memory" / "quizzes" / "hidden_humaneval.json"


def load_tasks(limit: int = 10, path: Path = HIDDEN) -> List[Dict[str, Any]]:
    """Hidden tasks in canonical form: id / title / objective / holdout_test.

    The file stores them as `prompt` / `hidden_test`; audits and grading both
    go through this loader, so they see exactly what the harness runs.
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
                "objective": t.get("prompt") or t.get("objective") or "",
                "holdout_test": t.get("hidden_test") or t.get("holdout_test") or "",
            }
        )
    return tasks[:limit] if limit and limit > 0 else tasks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    tasks = load_tasks(limit=args.limit)
    if not tasks:
        print(f"no hidden tasks in {HIDDEN}", file=sys.stderr)
        return 2

    leaks = audit_tasks(tasks)
    if leaks:
        print("REFUSING TO RUN — hidden tasks leak their own answers:", file=sys.stderr)
        for problem in leaks:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    pipe = Pipeline()
    rows = []
    t0 = time.perf_counter()
    for i, t in enumerate(tasks, 1):
        print(f"[hidden {i}/{len(tasks)}] {t['id']} ...", flush=True)
        # Generation sees the signature-only prompt. The asserts are appended
        # afterwards, in the sandbox, by core.holdout.grade_against_holdout.
        r = run_task(pipe, t["objective"], t["holdout_test"])
        graded = grade_run(r, t["holdout_test"])
        rows.append(
            {
                "id": t["id"],
                "gen_status": r.status,
                "hidden_ok": graded["ok"],
                "hidden_detail": graded["detail"],
                "exit": r.sandbox.exit_code if r.sandbox else None,
                "confidence": r.confidence,
            }
        )
        print(
            f"  hidden_ok={graded['ok']}"
            + (f" — {graded['detail']}" if not graded["ok"] and graded["detail"] else ""),
            flush=True,
        )

    passed = sum(1 for x in rows if x["hidden_ok"])
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "hidden_humaneval",
        "n": len(rows),
        "pass": passed,
        "pass_rate": round(passed / max(1, len(rows)), 3),
        "graded_on": "holdout",
        "duration_s": round(time.perf_counter() - t0, 2),
        "results": rows,
    }
    out = ROOT / "memory" / "quiz"
    out.mkdir(parents=True, exist_ok=True)
    (out / "hidden_latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    compute_health()
    try:
        write_scoreboard()
    except Exception:
        pass
    print(json.dumps({k: summary[k] for k in ("n", "pass", "pass_rate", "duration_s")}, indent=2))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
