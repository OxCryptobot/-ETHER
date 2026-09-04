"""Walk ExecutionPlan.steps in dependency order. Maps targets onto gems.protocol.

Does not run ToolRuntime. That is still Pipeline after plan. This is the DAG
walker Selenite was missing: steps[] are no longer a JSON dump.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from core.schemas import ExecutionPlan, PlanStep
from gems.protocol import by_id, registry_key

# PlanStep.target is free text. These aliases hit the typed registry.
TARGET_GEM = {
    "sandbox": "clear_quartz",
    "clear-quartz": "clear_quartz",
    "clear_quartz": "clear_quartz",
    "security": "black_tourmaline",
    "black-tourmaline": "black_tourmaline",
    "black_tourmaline": "black_tourmaline",
    "labradorite": "labradorite",
    "citrine": "citrine",
    "rose-quartz": "rose_quartz",
    "rose_quartz": "rose_quartz",
    "selenite": "selenite",
    "amethyst": "amethyst",
    "grandidierite": "grandidierite",
    "code": "rose_quartz",
    "codebase": "selenite",
}


def topo_sort(plan: ExecutionPlan) -> List[PlanStep]:
    steps = {s.id: s for s in plan.steps}
    pending = set(steps)
    ready: List[PlanStep] = []
    seen: set[int] = set()
    while pending:
        progressed = False
        for sid in sorted(pending):
            step = steps[sid]
            if all(d in seen for d in step.deps):
                ready.append(step)
                seen.add(sid)
                pending.remove(sid)
                progressed = True
                break
        if not progressed:
            # cycle or missing dep — append remaining in id order
            for sid in sorted(pending):
                ready.append(steps[sid])
            break
    return ready


def walk_plan(plan: ExecutionPlan) -> List[Dict[str, Optional[str]]]:
    rows: List[Dict[str, Optional[str]]] = []
    for step in topo_sort(plan):
        gid = TARGET_GEM.get(step.target) or TARGET_GEM.get(step.target.replace("-", "_"))
        gem = by_id(gid) if gid else None
        rows.append(
            {
                "id": str(step.id),
                "action": step.action,
                "target": step.target,
                "gem": gem.id if gem else None,
                "key": registry_key(gem.id) if gem else None,
                "status": gem.status if gem else "unmapped",
            }
        )
    return rows
