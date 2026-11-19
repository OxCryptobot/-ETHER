"""p3_57/p3_58: annotate a loop stage with its gem. Pipeline.run calls this."""
from __future__ import annotations

from typing import Dict, List, Optional

from gems.protocol import registry_key
from gems.runtime import STAGE_GEM, gem_for_stage


def annotate_stage(stage: str) -> Dict[str, Optional[str]]:
    gem = gem_for_stage(stage)
    if gem is None:
        return {"stage": stage, "gem": None, "status": None, "key": None}
    return {
        "stage": stage,
        "gem": gem.id,
        "status": gem.status,
        "key": registry_key(gem.id),
    }


def annotate_all() -> List[Dict[str, Optional[str]]]:
    return [annotate_stage(stage) for stage in STAGE_GEM]
