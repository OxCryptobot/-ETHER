"""Selenite execute + plan stage mark. Peeled off Pipeline.run."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Set


def execute_selenite_plan(
    pipe: Any,
    result: Any,
    *,
    skip: Set[str],
    objective: str,
    tid: str,
    task_id: Any,
    available: list,
    write_progress: Callable[..., None],
    attempts: list,
    t0: float,
) -> Dict[str, Any]:
    from core.loop.plan_stage import apply_plan_skip, walk_current_plan
    from core.pipeline import StageResult
    from core.schemas import Envelope, SeleniteRequest, SeleniteResponse

    plan_res = None
    if apply_plan_skip(skip, objective, result, write_progress, tid):
        pass
    else:
        write_progress(tid, objective, "plan")
        plan_req = Envelope(
            task_id=task_id,
            target_gem="selenite",
            payload=SeleniteRequest(user_query=objective, available_tools=available),
        )
        plan_res = pipe.registry.execute(plan_req)
        pipe.orchestrator.process_response(plan_req, plan_res)
        if plan_res.error or not isinstance(plan_res.payload, SeleniteResponse):
            return {
                "fail": pipe._fail(
                    result,
                    "plan",
                    plan_res.error.message if plan_res.error else "plan failed",
                    t0,
                    attempts,
                ),
                "plan_res": None,
                "needs_tool": False,
            }
        result.plan = plan_res.payload.plan
        result.plan_ok = True
    try:
        walk_current_plan(result, tid, objective, write_progress)
    except Exception as exc:
        result.degraded.append(f"plan_walk:{type(exc).__name__}")
    needs_tool = bool(
        plan_res is not None and getattr(plan_res.payload, "needs_tool", False)
    )
    result.stages.append(
        StageResult(
            stage="plan",
            success=True,
            detail=f"{len(result.plan.steps)} steps tool={needs_tool}",
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
    )
    return {"fail": None, "plan_res": plan_res, "needs_tool": needs_tool}
