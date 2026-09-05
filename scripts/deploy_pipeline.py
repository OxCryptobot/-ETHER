#!/usr/bin/env python3
"""FAST deploy gate. Pytest subset, write artifacts/pipeline/last.json.

Does not farm medic. Does not claim a living agent. Host or GitHub Actions.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "pipeline" / "last.json"

GATES = (
    "tests/test_p1_medic_idle.py",
    "tests/test_p1_medic_fifo.py",
    "tests/test_p4_01_fix_dag.py",
    "tests/test_p4_02_labradorite_traces.py",
    "tests/test_p4_03_selenite_fix.py",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_gates() -> dict:
    argv = [sys.executable, "-m", "pytest", *GATES, "-q", "--tb=line"]
    try:
        proc = subprocess.run(argv, cwd=str(ROOT), timeout=180)
        rc = int(proc.returncode)
    except subprocess.TimeoutExpired:
        rc = 124
    payload = {
        "ok": rc == 0,
        "rc": rc,
        "gates": list(GATES),
        "ts": _now(),
        "schema": "ether_deploy_pipeline_v1",
        "note": "FAST deploy gate. Not a living-agent job.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    return payload


def main() -> int:
    return 0 if run_gates().get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
