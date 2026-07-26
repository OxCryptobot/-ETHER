#!/usr/bin/env python3
"""One intelligent flywheel cycle: curriculum objective + full gates + push."""

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

from core.dotenv import load_dotenv
from scripts.flywheel import cycle
from scripts.flywheel_intelligence import resolve_objective, after_agentic

load_dotenv(ROOT / ".env")


def main() -> int:
    objective, meta = resolve_objective()
    print(json.dumps({"curriculum": meta, "objective_preview": objective[:120]}, indent=2), flush=True)
    report = cycle(
        do_push=True,
        min_confidence=float(os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7")),
        max_retries=int(os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3")),
        objective=objective,
        run_doctor=True,
    )
    intel = after_agentic(bool(report.get("ok")), task_id="")
    report["intelligence"] = {**meta, **intel}
    out = ROOT / "memory" / "flywheel" / "latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": report.get("ok"),
                "confidence": (report.get("gates") or {}).get("confidence"),
                "curriculum_tier": meta.get("curriculum_tier"),
                "guardian": intel.get("guardian"),
                "pushed": report.get("pushed"),
            },
            indent=2,
        )
    )
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
