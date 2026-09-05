"""Phase 7 moonshots. LoRA is off-box on 4GB; scale plane is not capped."""
from __future__ import annotations

from typing import Any, Dict


def lora_ready() -> Dict[str, Any]:
    return {
        "ok": False,
        "reason": "off_box",
        "vram_min_gb": 12,
        "local_1650": True,
        "note": "Train LoRA off-box when VRAM >= 12GB. Serving can stay 4B.",
    }


def experimental_flags() -> Dict[str, Any]:
    from core.model_router import outsource_configured, select_backend, vram_mb

    backend = select_backend({"class": "live"})
    return {
        "lora": lora_ready(),
        "mesh": False,
        "swarm": False,
        "max_live_agents": 1,
        "scale": {
            "outsource_configured": outsource_configured(),
            "backend": backend.get("backend"),
            "model": backend.get("model"),
            "scalable": True,
            "vram_mb": vram_mb(),
        },
    }