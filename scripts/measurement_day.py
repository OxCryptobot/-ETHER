#!/usr/bin/env python3
"""A. Measurement day — expand, fast bench, quiz, compare, health gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(args: list[str], timeout: int = 7200) -> int:
    print("+" , " ".join(args), flush=True)
    return subprocess.run(args, cwd=str(ROOT)).returncode


def main() -> int:
    steps = [
        [PY, str(ROOT / "scripts" / "expand_holdout.py")],
        [PY, str(ROOT / "scripts" / "bench.py"), "--fast"],
        [PY, str(ROOT / "scripts" / "quiz.py"), "--limit", "10"],
        [PY, str(ROOT / "scripts" / "compare_run.py"), "--limit", "5"],
        [PY, "-c", "from core.health_metric import declare_healthy; import json; print(json.dumps(declare_healthy(), indent=2))"],
    ]
    codes = []
    for s in steps:
        codes.append(run(s))
    from core.health_metric import declare_healthy

    h = declare_healthy()
    print("MEASUREMENT_DAY", json.dumps({"step_codes": codes, "healthy": h}, indent=2))
    return 0 if h.get("healthy") else 1


if __name__ == "__main__":
    raise SystemExit(main())
