#!/usr/bin/env python3
"""PEP8 gate for the living loop + deploy scripts. FAST. Ruff if present."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(ROOT))

SCOPE = (
    "core/loop",
    "scripts/deploy_pipeline.py",
    "scripts/stand_down.py",
    "scripts/pep8_loop.py",
)


def review() -> dict:
    from core.pep8_reviewer import review_paths

    report = review_paths([ROOT / p for p in SCOPE])
    payload = {
        "ok": bool(report.ok) and int(report.n_critical) == 0,
        "tool": report.tool,
        "n_critical": int(report.n_critical),
        "n_warning": int(report.n_warning),
        "assessment": report.assessment,
        "schema": "ether_pep8_loop_v1",
    }
    print(json.dumps(payload, indent=2), flush=True)
    return payload


def main() -> int:
    return 0 if review().get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
