#!/usr/bin/env python3
"""One intelligent flywheel cycle: curriculum + verified promote + healthy flag."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ.setdefault("ETHER_CURRICULUM", "1")
os.environ.setdefault("ETHER_EXPERIENCE", "1")
os.environ.setdefault("ETHER_BENCH_GUARDIAN", "1")
os.environ.setdefault("ETHER_FLYWHEEL_PUSH", "1")
os.environ.setdefault("ETHER_GIT_RESET_OK", "1")
os.environ.setdefault("ETHER_CURRICULUM_FAIL_RATE", "0.4")

from core.dotenv import load_dotenv
from scripts.flywheel import cycle
from scripts.flywheel_intelligence import resolve_objective, after_agentic

load_dotenv(ROOT / ".env")


def main() -> int:
    objective, meta = resolve_objective()
    print(json.dumps({"curriculum": meta, "objective_preview": objective[:160]}, indent=2), flush=True)
    report = cycle(
        do_push=True,
        min_confidence=float(os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7")),
        max_retries=int(os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3")),
        objective=objective,
        run_doctor=True,
    )
    gates = report.get("gates") or {}
    intel = after_agentic(
        bool(report.get("ok")),
        task_id=str(meta.get("curriculum_id") or ""),
        verification_score=float(gates.get("verification_score") or gates.get("confidence") or 0),
        total_tests=int(gates.get("total_tests") or 0),
    )
    report["intelligence"] = {**meta, **intel}
    out = ROOT / "memory" / "flywheel" / "latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "confidence": gates.get("confidence"),
                "curriculum_tier": meta.get("curriculum_tier"),
                "guardian": intel.get("guardian"),
                "healthy": intel.get("healthy"),
                "pushed": report.get("pushed"),
            },
            indent=2,
        )
    )
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
