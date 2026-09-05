"""Phase 7 moonshots. Honest: LoRA is off-box on a 4GB 1650."""
from __future__ import annotations

from typing import Any, Dict


def lora_ready() -> Dict[str, Any]:
    return {
        "ok": False,
        "reason": "off_box",
        "vram_min_gb": 12,
        "local_1650": True,
        "note": "Do not train LoRA on the 1650. Host is the 4B chair, not a trainer.",
    }


def experimental_flags() -> Dict[str, Any]:
    return {
        "lora": lora_ready(),
        "mesh": False,
        "swarm": False,
        "max_live_agents": 1,
    }
