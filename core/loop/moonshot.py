"""Phase 7 moonshots. LoRA trainer is Grok (git bus), not the 1650."""
from __future__ import annotations

from typing import Any, Dict


def lora_ready() -> Dict[str, Any]:
    from core.loop.lora_pack import lora_status

    return lora_status()


def experimental_flags() -> Dict[str, Any]:
    from core.model_router import grok_present, outsource_configured, select_backend, vram_mb

    backend = select_backend({"class": "live"})
    return {
        "lora": lora_ready(),
        "mesh": False,
        "swarm": False,
        "max_live_agents": 1,
        "scale": {
            "outsource_configured": outsource_configured(),
            "grok_present": grok_present(),
            "backend": backend.get("backend"),
            "model": backend.get("model"),
            "scalable": True,
            "vram_mb": vram_mb(),
        },
    }
