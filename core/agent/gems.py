"""ReAct routes each step to a gem. Theatre gems are not called."""
from __future__ import annotations

from typing import Any, Dict

from gems.protocol import by_id, live_gems


STAGE_GEM = {
    "plan": "selenite",
    "route": "rose_quartz",
    "sandbox": "clear_quartz",
    "memory": "citrine",
    "profile": "labradorite",
    "evolve": "amethyst",
    "security": "black_tourmaline",
    "fabricate": "grandidierite",
}


def route_stage(stage: str) -> Dict[str, Any]:
    """One stage. A theatre gem is skipped. A live gem is named."""
    gid = STAGE_GEM.get(stage)
    if gid is None:
        return {"ok": False, "stage": stage, "reason": "unknown"}
    gem = by_id(gid)
    if gem is None:
        return {"ok": False, "stage": stage, "reason": "missing"}
    if gem.status == "theatre":
        return {"ok": False, "stage": stage, "gem": gid, "reason": "theatre", "writes": False}
    return {"ok": True, "stage": stage, "gem": gid, "role": gem.role, "status": gem.status, "writes": False}


def memory(root, note: str) -> Dict[str, Any]:
    """Citrine stage. The trace is stored. The next prompt may see it."""
    row = route_stage("memory")
    if not row["ok"]:
        return row
    from core.agent.sota import remember

    remember(root, "trace", note[:180], kept=False)
    return {**row, "stored": note[:180]}


def live() -> list:
    """The gems that can run. The rest stay named."""
    return [g.id for g in live_gems()]
