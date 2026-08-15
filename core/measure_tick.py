"""Phase 3.4/3.6 — always-safe measurement tick + honest KPI."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "measure_tick.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run() -> Dict[str, Any]:
    steps: Dict[str, Any] = {}
    errors: List[str] = []

    try:
        from core.honest_live import publish

        rates = publish()
        steps["honest_live"] = {
            "ok": True,
            "status": rates.get("status"),
            "live_n": rates.get("live_n"),
            "live_honest_rate": rates.get("live_honest_rate"),
            "soft_launch_blocked": rates.get("soft_launch_blocked"),
        }
    except Exception as e:
        errors.append(f"honest_live:{type(e).__name__}:{e}")
        steps["honest_live"] = {"ok": False, "error": str(e)[:200]}

    try:
        from core.honest_kpi import compute

        kpi = compute()
        steps["honest_kpi"] = {
            "ok": bool(kpi.get("ok")),
            "primary_kpi": kpi.get("primary_kpi"),
            "honest_tool_pass": kpi.get("honest_tool_pass"),
            "tool_attempts": kpi.get("tool_attempts"),
            "disguised_pass_n": kpi.get("disguised_pass_n"),
        }
    except Exception as e:
        errors.append(f"honest_kpi:{type(e).__name__}:{e}")
        steps["honest_kpi"] = {"ok": False, "error": str(e)[:200]}

    try:
        from core.phase3_snapshot import build_snapshot

        snap = build_snapshot()
        steps["phase3_snapshot"] = {
            "ok": bool(snap.get("ok")),
            "path": snap.get("path"),
            "trained": (snap.get("lora_dry_tick") or {}).get("trained"),
        }
    except Exception as e:
        errors.append(f"phase3_snapshot:{type(e).__name__}:{e}")
        steps["phase3_snapshot"] = {"ok": False, "error": str(e)[:200]}

    try:
        from core.soft_launch import evaluate

        gate = evaluate()
        steps["soft_launch"] = {
            "ok": True,
            "soft_launch_ready": gate.get("soft_launch_ready"),
            "blocked_reasons": gate.get("blocked_reasons"),
            "path": gate.get("path"),
        }
    except Exception as e:
        errors.append(f"soft_launch:{type(e).__name__}:{e}")
        steps["soft_launch"] = {"ok": False, "error": str(e)[:200]}

    try:
        from core.queue_governor import status_snapshot

        steps["governor"] = status_snapshot()
    except Exception as e:
        steps["governor"] = {"error": str(e)[:120]}

    report: Dict[str, Any] = {
        "timestamp": _now(),
        "ok": len(errors) == 0,
        "errors": errors,
        "steps": steps,
        "soft_launch_blocked": True,
        "doctrine": "measure_only_critical_ops",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return report


if __name__ == "__main__":
    import sys

    out = run()
    print(json.dumps(out, indent=2))
    sys.exit(0)
