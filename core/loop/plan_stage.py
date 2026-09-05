"""Pipeline plan skip + walk. Strangler slice off the 76kB god-file."""
from __future__ import annotations

from typing import Any, Callable, List


def apply_plan_skip(
    skip: set,
    objective: str,
    result: Any,
    write_progress: Callable[..., None],
    tid: str,
) -> bool:
    """True when Selenite is skipped and fix_plan is installed."""
    if "plan" not in skip:
        return False
    from core.loop.fix_dag import fix_plan

    result.plan = fix_plan(objective)
    result.plan_ok = True
    write_progress(tid, objective, "plan", detail="skipped_resume_fix_dag")
    return True


def walk_current_plan(
    result: Any,
    tid: str,
    objective: str,
    write_progress: Callable[..., None],
) -> List[dict]:
    from core.loop.plan_exec import dispatch_walked, execute_dispatched
    from core.loop.plan_walk import walk_plan

    walked = execute_dispatched(dispatch_walked(walk_plan(result.plan)))
    write_progress(
        tid,
        objective,
        "plan_walk",
        detail=",".join(
            f"{r['id']}:{r['action']}:{r.get('tool') or r['gem'] or r['status']}" for r in walked
        ),
    )
    return walked
