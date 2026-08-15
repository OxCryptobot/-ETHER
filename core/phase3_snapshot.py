"""Phase 3 soft-launch measurement snapshot.

Publishes artifacts/phase3_snapshot.json. Does not lift training wheels.
Does not train. Does not flip soft launch.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "phase3_snapshot.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_snapshot() -> Dict[str, Any]:
    rates: Dict[str, Any] = {}
    dry: Dict[str, Any] = {}
    errors: list[str] = []

    try:
        from core.honest_live import publish as publish_rates

        rates = publish_rates()
    except Exception as e:
        errors.append(f"honest_live:{type(e).__name__}:{e}")

    try:
        from core.lora_dry_tick import dry_tick

        dry = dry_tick(force=True)
    except Exception as e:
        errors.append(f"lora_dry:{type(e).__name__}:{e}")

    from core.loop import decide_tool_first_terminal, loop_runner_enabled
    from core.symbol_index import symbol_index_enabled

    gate_pass = decide_tool_first_terminal(enabled=True, done_ok=True, score=1.0)
    gate_fail = decide_tool_first_terminal(enabled=True, done_ok=False, error="max_steps")

    snap: Dict[str, Any] = {
        "timestamp": _now(),
        "phase": "3",
        "soft_launch_blocked": True,
        "training_wheels": True,
        "flags": {
            "ETHER_LOOP_RUNNER": loop_runner_enabled(),
            "ETHER_SYMBOL_INDEX": symbol_index_enabled(),
        },
        "honest_live": rates,
        "lora_dry_tick": {
            "ok": dry.get("ok"),
            "trained": dry.get("trained"),
            "dry_run": dry.get("dry_run"),
            "path": dry.get("path"),
        },
        "tool_first_gate": {
            "pass_ok": gate_pass.ok,
            "pass_terminal": gate_pass.terminal,
            "fail_ok": gate_fail.ok,
            "fail_terminal": gate_fail.terminal,
            "fail_degraded": list(gate_fail.degraded),
        },
        "errors": errors,
        "ok": not errors and dry.get("ok", False) is True,
        "note": (
            "Measurement only. Soft launch requires expanded hard suite "
            "live_honest_rate + mentor sign-off."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    snap["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return snap


if __name__ == "__main__":
    import sys

    out = build_snapshot()
    print(json.dumps(out, indent=2))
    sys.exit(0 if out.get("ok") else 1)
