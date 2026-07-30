#!/usr/bin/env python3
"""Run MBPP-lite + hidden HumanEval-style with signature-only prompts.

The prompts here were already clean — they describe behaviour and keep their
assertions in `hidden_test`. The GRADING was not: this script re-implemented
the concatenate-and-run step inline and scored
`ok = not sand.error and exit_code == 0`, the same defect as
scripts/hidden_quiz.py. A `sys.exit(0)` ahead of the appended asserts, or a
`hidden_test` with nothing observable in it, both graded as a pass, and the
model's own module-level asserts ran before the hidden ones (so one bad
self-assert failed a correct answer).

Grading now goes through `core.holdout.grade_against_holdout` (via the shared
adapter in scripts/bench.py), which strips the model's top-level asserts,
requires at least one real held-out assertion, refuses to grade a holdout that
already appears in the generated code, and demands an unpredictable sentinel on
stdout so an early clean exit cannot pass.
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
from core.scoreboard import write_scoreboard
from core.health_metric import compute_health

# Shared auditor/grader — see scripts/bench.py. core.holdout does the work.
from scripts.bench import audit_tasks, grade_run, run_task

load_dotenv(ROOT / ".env")

SOURCES = (
    ROOT / "memory" / "quizzes" / "hidden_humaneval.json",
    ROOT / "memory" / "datasets" / "mbpp_lite.json",
)


def load_tasks(limit: int = 12, sources=SOURCES) -> List[Dict[str, Any]]:
    """Tasks from every dataset, in canonical id/objective/holdout_test form.

    This function — not the JSON files — is what the harness runs, so it is
    also what a leak audit has to inspect. The equivalent curriculum test read
    the shipped JSON directly and was blind to everything its loader spliced in
    at runtime.
    """
    tasks: List[Dict[str, Any]] = []
    for path in sources:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for t in data.get("tasks") or []:
            tasks.append(
                {
                    "id": t.get("id") or "",
                    "title": t.get("title") or t.get("id") or "",
                    "objective": t.get("prompt") or t.get("objective") or "",
                    "holdout_test": t.get("hidden_test") or t.get("holdout_test") or "",
                    "source": path.name,
                }
            )
    return tasks[:limit] if limit and limit > 0 else tasks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()
    tasks = load_tasks(limit=args.limit)
    if not tasks:
        print(
            "no dataset tasks found — run scripts/fetch_datasets.py "
            "(Day-3: eval data is untracked) or restore local copies",
            file=sys.stderr,
        )
        return 2

    leaks = audit_tasks(tasks)
    if leaks:
        print("REFUSING TO RUN — dataset tasks leak their own answers:", file=sys.stderr)
        for problem in leaks:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    pipe = Pipeline()
    rows = []
    t0 = time.perf_counter()
    for i, t in enumerate(tasks, 1):
        tid = t.get("id")
        print(f"[dataset {i}/{len(tasks)}] {tid}", flush=True)
        r = run_task(pipe, t["objective"], t["holdout_test"])
        graded = grade_run(r, t["holdout_test"])
        rows.append(
            {
                "id": tid,
                "source": t.get("source"),
                "ok": graded["ok"],
                "detail": graded["detail"],
                "conf": r.confidence,
            }
        )
        print(
            f"  ok={graded['ok']}"
            + (f" — {graded['detail']}" if not graded["ok"] and graded["detail"] else ""),
            flush=True,
        )

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "dataset_hidden",
        "n": len(rows),
        "pass": sum(1 for x in rows if x["ok"]),
        "pass_rate": round(sum(1 for x in rows if x["ok"]) / max(1, len(rows)), 3),
        "graded_on": "holdout",
        "duration_s": round(time.perf_counter() - t0, 2),
        "results": rows,
    }
    out = ROOT / "memory" / "quiz"
    out.mkdir(parents=True, exist_ok=True)
    (out / "dataset_latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    # feed health via quiz timestamp if no holdout quiz has run yet
    if not (out / "latest.json").exists():
        (out / "latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    compute_health()
    write_scoreboard()
    print(json.dumps({k: summary[k] for k in ("n", "pass", "pass_rate")}, indent=2))
    return 0 if summary["pass"] == summary["n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
