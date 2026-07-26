#!/usr/bin/env python3
"""Dense, dated scoreboard — bench + quiz + dataset + optional ablation stub."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(args: list[str], timeout: int = 7200) -> int:
    print("+", " ".join(args), flush=True)
    return subprocess.run(args, cwd=str(ROOT)).returncode


def main() -> int:
    steps = [
        [PY, str(ROOT / "scripts" / "expand_holdout.py")],
        [PY, str(ROOT / "scripts" / "git_curriculum_miner.py")],
        [PY, str(ROOT / "scripts" / "bench.py"), "--fast"],
        [PY, str(ROOT / "scripts" / "quiz.py"), "--limit", "10"],
        [PY, str(ROOT / "scripts" / "dataset_quiz.py"), "--limit", "8"],
        [PY, str(ROOT / "scripts" / "compare_run.py"), "--limit", "5"],
        [PY, "-c", "from core.scoreboard import write_scoreboard; print(write_scoreboard())"],
        [PY, "-c", "from core.health_metric import declare_healthy; import json; print(json.dumps(declare_healthy(), indent=2))"],
    ]
    codes = [run(s) for s in steps]
    archive = ROOT / "memory" / "bench" / f"weekly_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "step_codes": codes,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("WEEKLY DONE", codes)
    return 0 if codes and codes[-1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
