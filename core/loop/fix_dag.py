"""Fix-task DAG: observe → mutate → run_tests → validate.

Phase 4 reasoning slice. Selenite JSON is not a planner; this walker is.
Does not spawn agents. One consumer. Tools are intents until ToolRuntime.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.schemas import ExecutionPlan, PlanStep

FIX_STEPS = (
    (1, "observe", "codebase", ()),
    (2, "mutate", "code", (1,)),
    (3, "test", "sandbox", (2,)),
    (4, "validate", "security", (3,)),
)


def fix_plan(objective: str = "fix") -> ExecutionPlan:
    return ExecutionPlan(
        reasoning=objective,
        steps=[
            PlanStep(
                id=sid,
                action=action,
                target=target,
                deps=list(deps),
                description=objective,
            )
            for sid, action, target, deps in FIX_STEPS
        ],
    )


def walk_fix(objective: str = "fix") -> List[Dict[str, Optional[str]]]:
    from core.loop.plan_exec import dispatch_walked
    from core.loop.plan_walk import walk_plan

    return dispatch_walked(walk_plan(fix_plan(objective)))


def tool_order(rows: List[Dict[str, Optional[str]]]) -> List[str]:
    return [str(r.get("tool") or r.get("dispatched") or "") for r in rows]


def execute_fix(objective: str = "fix") -> Dict[str, Any]:
    """Dispatch only. Does not claim unaided living-agent."""
    from core.loop.plan_exec import execute_dispatched

    rows = walk_fix(objective)
    executed = execute_dispatched(rows)
    return {
        "ok": True,
        "objective": objective,
        "n": len(executed),
        "tools": tool_order(rows),
        "ids": [r.get("id") for r in rows],
        "rows": executed,
    }
