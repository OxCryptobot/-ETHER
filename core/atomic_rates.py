"""Atomic rates publish — single source of truth for gate metrics.

Phase C (2026-08-22): eligible_rates → phase1_gate → honest_live in one
call so Control Matrix never shows divergent live_eligible_n / honest_rate.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "atomic_rates.json"


def publish() -> Dict[str, Any]:
    errors = []
    elig: Dict[str, Any] = {}
    gate: Dict[str, Any] = {}
    honest: Dict[str, Any] = {}

    try:
        from core.eligible_rates import compute as elig_compute

        elig = elig_compute()
    except Exception as e:
        errors.append(f"eligible_rates:{type(e).__name__}:{e}")
        elig = {"ok": False, "error": str(e)[:160]}

    try:
        from core.phase1_gate import compute as gate_compute

        gate = gate_compute()
    except Exception as e:
        errors.append(f"phase1_gate:{type(e).__name__}:{e}")
        gate = {"ok": False, "error": str(e)[:160]}

    try:
        from core.honest_live import publish as honest_publish

        honest = honest_publish()
    except Exception as e:
        errors.append(f"honest_live:{type(e).__name__}:{e}")
        honest = {"ok": False, "error": str(e)[:160]}

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "ok": len(errors) == 0,
        "errors": errors,
        "eligible": {
            "live_eligible_n": elig.get("live_eligible_n"),
            "honest_rate_eligible": elig.get("honest_rate_eligible"),
            "timeout_rate_eligible": elig.get("timeout_rate_eligible"),
            "honest_eligible_n": elig.get("honest_eligible_n"),
            "metrics_ok": elig.get("metrics_ok"),
        },
        "phase1_gate": {
            "status": gate.get("status"),
            "metrics_go": gate.get("metrics_go"),
            "architecture_go": gate.get("architecture_go"),
            "honest_rate_eligible": gate.get("honest_rate_eligible"),
            "live_eligible_n": gate.get("live_eligible_n"),
            "checks_ok": gate.get("checks_ok"),
            "checks_n": gate.get("checks_n"),
        },
        "honest_live": {
            "live_honest_rate": honest.get("live_honest_rate"),
            "live_n": honest.get("live_n"),
            "status": honest.get("status"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
