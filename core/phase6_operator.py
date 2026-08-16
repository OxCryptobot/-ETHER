"""Phase 6 — operator CLI surface canary.

Verifies ether_cli commands are importable and return expected shapes.
Does not start host. Does not lift wheels.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase6_operator.json"


def run_canary() -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        cases.append({"name": name, "pass": bool(ok), "detail": detail[:120]})

    try:
        from scripts import ether_cli as cli

        add("import_cli", True, "scripts.ether_cli")
        for cmd in ("status", "queue", "phase", "next", "doctor"):
            add(f"has_cmd_{cmd}", hasattr(cli, f"cmd_{cmd}"), cmd)
        # smoke invoke
        rc = cli.cmd_status(None)  # type: ignore[arg-type]
        add("cmd_status_rc", rc == 0, f"rc={rc}")
        rc2 = cli.cmd_phase(None)  # type: ignore[arg-type]
        add("cmd_phase_rc", rc2 == 0, f"rc={rc2}")
        # doctor may return 1 on warnings — allow 0 or 1
        rc3 = cli.cmd_doctor(None)  # type: ignore[arg-type]
        add("cmd_doctor_rc", rc3 in (0, 1), f"rc={rc3}")
    except Exception as e:
        add("import_cli", False, str(e))

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    add("wheels_on", wheels, f"wheels={wheels}")

    passed = sum(1 for c in cases if c["pass"])
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "6",
        "n": len(cases),
        "passed": passed,
        "ok": passed == len(cases),
        "cases": cases,
        "note": "Operator CLI canary. Host process not started by this module.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_canary(), indent=2))
