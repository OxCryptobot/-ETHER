"""LoRA dry tick — Phase 2.5 continuous evolution *signal* without weight updates.

Hard rules:
  - Always dry-run. Never calls real train backends.
  - Never writes adapter.pth or mutates base weights.
  - Safe under training wheels; safe if flags are accidentally set.
  - Publishes artifacts/lora_dry_tick.json for Control Matrix / steady jobs.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
TICK_PATH = ARTIFACTS / "lora_dry_tick.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dry_tick(*, force: bool = True) -> Dict[str, Any]:
    """One observability tick. force=True means refuse real train even if env unlocked."""
    from core.lora_train import dry_run_report, train_adapter

    readiness = dry_run_report()
    # HARD: this module never trains. Strip promote/train for the duration.
    prev_train = os.environ.get("ETHER_LORA_TRAIN")
    prev_promote = os.environ.get("ETHER_LORA_PROMOTE")
    try:
        if force:
            os.environ["ETHER_LORA_TRAIN"] = "0"
            os.environ["ETHER_LORA_PROMOTE"] = "0"
        result = train_adapter(dry_run=True)
    finally:
        if force:
            if prev_train is None:
                os.environ.pop("ETHER_LORA_TRAIN", None)
            else:
                os.environ["ETHER_LORA_TRAIN"] = prev_train
            if prev_promote is None:
                os.environ.pop("ETHER_LORA_PROMOTE", None)
            else:
                os.environ["ETHER_LORA_PROMOTE"] = prev_promote

    report: Dict[str, Any] = {
        "timestamp": _now(),
        "ok": bool(result.get("ok")),
        "dry_run": True,
        "forced_dry": True,
        "trained": False,
        "adapter_written": False,
        "readiness": readiness,
        "train_adapter": {
            "ok": result.get("ok"),
            "dry_run": result.get("dry_run"),
            "forced_dry_run": result.get("forced_dry_run"),
            "message": result.get("message") or result.get("error"),
            "report_path": result.get("report_path"),
        },
        "doctrine": "dry_tick_only_phase_2_5",
        "next": (
            "Keep collecting preference pairs. Real train only after "
            "ETHER_LORA_TRAIN=1 + ETHER_LORA_PROMOTE=1 + green preference health."
        ),
    }

    # Safety asserts — never claim train happened from this path
    if result.get("adapter_path"):
        report["ok"] = False
        report["error"] = "unexpected_adapter_path_on_dry_tick"
    if result.get("dry_run") is False:
        report["ok"] = False
        report["error"] = "dry_run_false_on_dry_tick"

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    TICK_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["path"] = str(TICK_PATH.relative_to(ROOT)).replace("\\", "/")
    return report


if __name__ == "__main__":
    import sys

    out = dry_tick()
    print(json.dumps(out, indent=2))
    sys.exit(0 if out.get("ok") else 1)
