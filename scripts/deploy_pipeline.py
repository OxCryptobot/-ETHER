#!/usr/bin/env python3
"""FAST leftover gate. Pytest suite, write artifacts/pipeline/last.json."""
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
    "tests/test_p2_pep8_resume_plan.py",
    "tests/test_p3_75_living_fabricate.py",
    "tests/test_p4_01_fix_dag.py",
    "tests/test_p4_02_labradorite_traces.py",
    "tests/test_p4_03_selenite_fix.py",
    "tests/test_up_01_flywheel.py",
    "tests/test_remaining_34.py",
    "tests/test_scale_plane.py",
    "tests/test_deploy_pipeline.py",
    "tests/test_leftover_gate.py",
    "tests/test_goal.py",
    "tests/test_begin.py",
    "tests/test_plan_stage.py",
    "tests/test_tools_avail.py",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_gates() -> dict:
    argv = [sys.executable, "-m", "pytest", *GATES, "-q", "--tb=line"]
    stdout = ""
    stderr = ""
    try:
        proc = subprocess.run(
            argv, cwd=str(ROOT), timeout=240, capture_output=True, text=True
        )
        rc = int(proc.returncode)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired:
        rc = 124
    payload = {
        "ok": rc == 0,
        "rc": rc,
        "gates": list(GATES),
        "n_gates": len(GATES),
        "failed": [ln for ln in stdout.splitlines() if ln.startswith("FAILED")],
        "tail": (stdout + "\n" + stderr)[-2500:],
        "ts": _now(),
        "schema": "ether_deploy_pipeline_v1",
        "note": "FAST leftover gate. Not a living-agent job. Not LoRA.",
    }
    print(stdout, end="", flush=True)
    if stderr:
        print(stderr, end="", file=sys.stderr, flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    return payload


def main() -> int:
    return 0 if run_gates().get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
