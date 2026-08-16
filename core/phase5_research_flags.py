"""Phase 5 — experimental research flags (must stay OFF by default).

Central board so experiments cannot silently enable.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase5_research_flags.json"

# env var → description; default must be off
FLAGS: List[Dict[str, str]] = [
    {"env": "ETHER_PIPELINE_TERMINAL", "desc": "Wire pure terminal into Pipeline"},
    {"env": "ETHER_LOOP_RUNNER", "desc": "Loop runner live path"},
    {"env": "ETHER_SYMBOL_INDEX", "desc": "Symbol index in Pipeline"},
    {"env": "ETHER_SOFT_LAUNCH", "desc": "Soft launch"},
    {"env": "ETHER_LORA_TRAIN", "desc": "LoRA train"},
    {"env": "ETHER_LORA_PROMOTE", "desc": "LoRA promote"},
    {"env": "ETHER_AUTO_PROMOTE", "desc": "Auto-promote fabricated tools"},
    {"env": "ETHER_SHADOW_LIVE", "desc": "Parallel live shadow oracle"},
    {"env": "ETHER_SWARM_LIVE", "desc": "Multi-agent GPU swarm"},
    {"env": "ETHER_MCP_SERVER", "desc": "Live MCP HTTP server"},
]


def board() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    any_on = False
    for f in FLAGS:
        on = (os.getenv(f["env"]) or "0").strip() in ("1", "true", "TRUE", "yes")
        if on:
            any_on = True
        rows.append({"env": f["env"], "desc": f["desc"], "on": on, "must_default_off": True})

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "5",
        "flags": rows,
        "any_experimental_on": any_on,
        "training_wheels": wheels,
        "ok": (not any_on) and wheels,
        "note": "Research board. Experimental ON flags fail this canary until intentional.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(board(), indent=2))
