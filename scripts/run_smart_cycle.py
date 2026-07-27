#!/usr/bin/env python3
"""One intelligent flywheel cycle: curriculum + verified promote + autonomy hooks."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from core.dotenv import load_dotenv

# .env must load BEFORE these setdefault() calls — the loader never overrides
# an already-set variable, so doing it the other way round silently ignored an
# operator's ETHER_FLYWHEEL_PUSH=0 and force-enabled ETHER_GIT_RESET_OK.
load_dotenv(ROOT / ".env")

os.environ.setdefault("ETHER_CURRICULUM", "1")
os.environ.setdefault("ETHER_EXPERIENCE", "1")
os.environ.setdefault("ETHER_BENCH_GUARDIAN", "1")
os.environ.setdefault("ETHER_FLYWHEEL_PUSH", "1")
os.environ.setdefault("ETHER_GIT_RESET_OK", "1")
os.environ.setdefault("ETHER_CURRICULUM_FAIL_RATE", "0.4")
os.environ.setdefault("ETHER_AUTO_ENQUEUE", "1")

from scripts.flywheel import cycle
from scripts.flywheel_intelligence import resolve_objective, after_agentic


def main() -> int:
    objective, meta = resolve_objective()
    print(json.dumps({"curriculum": meta, "objective_preview": objective[:200]}, indent=2), flush=True)
    report = cycle(
        # Was hardcoded True. flywheel.cycle() computes
        # `want_push = do_push or ETHER_FLYWHEEL_PUSH == "1"`, so a hardcoded
        # True made the env var unable to suppress a push — an operator who
        # set ETHER_FLYWHEEL_PUSH=0 still pushed to the shared remote.
        do_push=os.getenv("ETHER_FLYWHEEL_PUSH", "0") == "1",
        min_confidence=float(os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7")),
        max_retries=int(os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3")),
        objective=objective,
        run_doctor=True,
        # Graded on assertions the generator never saw. Carried separately
        # from the objective so it cannot leak into the prompt.
        holdout_test=str(meta.get("holdout_test") or ""),
    )
    gates = report.get("gates") or {}
    agentic = report.get("agentic") or {}
    final = {}
    attempts = agentic.get("attempts") or []
    if attempts:
        final = attempts[-1]
    # Prefer explicit verification fields if cycle recorded them
    verification_score = float(
        gates.get("verification_score")
        or final.get("verification_score")
        or gates.get("confidence")
        or 0
    )
    total_tests = int(gates.get("total_tests") or final.get("total_tests") or 0)
    fail_kind = str(final.get("fail_kind") or gates.get("agentic_reason") or "runtime")
    stderr = str(final.get("stderr") or "")

    intel = after_agentic(
        bool(report.get("ok")),
        task_id=str(meta.get("curriculum_id") or final.get("task_id") or ""),
        verification_score=verification_score,
        total_tests=total_tests,
        objective=objective,
        fail_kind=fail_kind,
        stderr=stderr,
    )
    report["intelligence"] = {**meta, **intel}
    report["gates"] = {
        **gates,
        "verification_score": verification_score,
        "total_tests": total_tests,
    }
    out = ROOT / "memory" / "flywheel" / "latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "confidence": gates.get("confidence"),
                "verification_score": verification_score,
                "total_tests": total_tests,
                "curriculum_tier": meta.get("curriculum_tier"),
                "guardian": intel.get("guardian"),
                "healthy": intel.get("healthy"),
                "autonomy": intel.get("autonomy"),
                "pushed": report.get("pushed"),
            },
            indent=2,
        )
    )
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
