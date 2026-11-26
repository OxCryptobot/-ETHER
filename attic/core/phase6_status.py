"""Phase 6 status — operator OS / production readiness under wheels.

OPERATOR_COMPLETE when CLI canary, phase board, and host-heal contracts pass.
Soft launch and auto-ops remain LOCKED.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase6_status.json"


def compute() -> Dict[str, Any]:
    packages: List[Dict[str, Any]] = []

    def pkg(pid: str, name: str, ok: bool, detail: str = "") -> None:
        packages.append(
            {"id": pid, "name": name, "ok": bool(ok), "detail": detail[:160]}
        )

    try:
        from core.phase6_operator import run_canary

        o = run_canary()
        pkg("6-operator", "Operator CLI canary", bool(o.get("ok")), f"{o.get('passed')}/{o.get('n')}")
    except Exception as e:
        pkg("6-operator", "Operator CLI canary", False, str(e))

    try:
        from core.phase6_phase_board import board

        b = board()
        pkg("6-board", "Unified phase board", bool(b.get("ok")), f"rows={b.get('n')}")
    except Exception as e:
        pkg("6-board", "Unified phase board", False, str(e))

    try:
        from core.phase6_host_heal import check

        h = check()
        pkg("6-host-heal", "Host self-heal contracts", bool(h.get("ok")), f"{h.get('passed')}/{h.get('n')}")
    except Exception as e:
        pkg("6-host-heal", "Host self-heal contracts", False, str(e))

    try:
        from core.phase5_status import compute as p5

        p5s = p5()
        pkg(
            "6-phase5-prereq",
            "Phase 5 experiment prerequisite",
            bool(p5s.get("experiment_complete")) or p5s.get("status") == "EXPERIMENT_COMPLETE",
            str(p5s.get("status")),
        )
    except Exception as e:
        pkg("6-phase5-prereq", "Phase 5 experiment prerequisite", False, str(e))

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    pkg("6-wheels", "Training wheels ON", wheels, f"wheels={wheels}")

    core_ids = {"6-operator", "6-board", "6-host-heal", "6-wheels"}
    core = [p for p in packages if p["id"] in core_ids]
    complete = all(p["ok"] for p in core)

    locked = [
        {
            "id": "6B-unattended-soft-launch",
            "name": "Unattended soft launch",
            "status": "LOCKED",
            "reason": "metrics_go + human flags required",
        },
        {
            "id": "6C-auto-host-restart",
            "name": "OS-level auto host restart service",
            "status": "LOCKED",
            "reason": "Windows service packaging is operator install step",
        },
        {
            "id": "6D-remote-ops",
            "name": "Remote operator API",
            "status": "LOCKED",
            "reason": "local-first; no public bind",
        },
    ]

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "6",
        "name": "Operator OS / readiness",
        "operator_complete": complete,
        "status": "OPERATOR_COMPLETE" if complete else "OPERATOR_IN_PROGRESS",
        "packages": packages,
        "packages_ok": sum(1 for p in packages if p["ok"]),
        "packages_n": len(packages),
        "locked": locked,
        "training_wheels": wheels,
        "soft_launch_blocked": True,
        "note": (
            "Phase 6 complete = CLI + phase board + host-heal contracts under wheels. "
            "Not soft launch."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
