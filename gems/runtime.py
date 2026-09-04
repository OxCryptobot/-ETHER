"""Stage → gem dispatch. Pipeline.run calls annotate_all() at start (p3_58)."""
from __future__ import annotations

from typing import Dict, Optional

from gems.protocol import GemSpec, by_id

STAGE_GEM: Dict[str, str] = {
    "plan": "selenite",
    "tool_runtime": "rose_quartz",
    "sandbox": "clear_quartz",
    "audit": "black_tourmaline",
    "critique": "labradorite",
    "holdout": "clear_quartz",
    "prompt_guard": "black_tourmaline",
    "memory_save": "citrine",
    "auto_fabricate": "grandidierite",
}


def gem_for_stage(stage: str) -> Optional[GemSpec]:
    gid = STAGE_GEM.get(stage)
    return by_id(gid) if gid else None
