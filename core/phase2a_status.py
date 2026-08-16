"""Phase 2A status — canaries + architecture_go, wheels stay ON."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase2a_status.json"


def compute() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    try:
        from core.pipeline_terminal_canary import run_matrix as tcan

        t = tcan()
        checks.append(
            {
                "id": "terminal_canary",
                "ok": bool(t.get("ok")),
                "detail": f"{t.get('passed')}/{t.get('n')}",
            }
        )
    except Exception as e:
        checks.append({"id": "terminal_canary", "ok": False, "detail": str(e)[:80]})

    try:
        from core.pipeline_score_canary import run_matrix as scan

        s = scan()
        checks.append(
            {
                "id": "score_canary",
                "ok": bool(s.get("ok")),
                "detail": f"{s.get('passed')}/{s.get('n')}",
            }
        )
    except Exception as e:
        checks.append({"id": "score_canary", "ok": False, "detail": str(e)[:80]})

    try:
        from core.pipeline_adapter import terminal_adapter_enabled

        checks.append(
            {
                "id": "adapter_off",
                "ok": terminal_adapter_enabled() is False,
                "detail": f"enabled={terminal_adapter_enabled()}",
            }
        )
    except Exception as e:
        checks.append({"id": "adapter_off", "ok": False, "detail": str(e)[:80]})

    arch_go = False
    try:
        from core.phase1_gate import compute as gate

        g = gate()
        arch_go = bool(g.get("architecture_go"))
        checks.append(
            {
                "id": "architecture_go",
                "ok": arch_go,
                "detail": f"status={g.get('status')} metrics_go={g.get('metrics_go')}",
            }
        )
    except Exception as e:
        checks.append({"id": "architecture_go", "ok": False, "detail": str(e)[:80]})

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    checks.append({"id": "wheels_on", "ok": wheels, "detail": f"wheels={wheels}"})

    ok_n = sum(1 for c in checks if c["ok"])
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "2A",
        "name": "Strangler canaries under wheels",
        "status": "PASS" if ok_n == len(checks) else "PARTIAL",
        "checks_ok": ok_n,
        "checks_n": len(checks),
        "checks": checks,
        "architecture_go": arch_go,
        "soft_launch_blocked": True,
        "note": "2A = pure canaries only. No LIVE. No soft launch. Adapter OFF.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
