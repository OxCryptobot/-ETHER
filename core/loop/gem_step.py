"""p3_57: annotate a loop stage with its gem. Pipeline.run can call this later."""
from __future__ import annotations

from typing import Any, Dict, Optional

from gems.runtime import gem_for_stage


def annotate_stage(stage: str) -> Dict[str, Optional[str]]:
    gem = gem_for_stage(stage)
    if gem is None:
        return {"stage": stage, "gem": None, "status": None}
    return {"stage": stage, "gem": gem.id, "status": gem.status}
