"""Plan-extend / tool_run peeled off Pipeline.run."""
from __future__ import annotations

import time
from typing import Any, Callable, Optional


def run_extend_if_needed(
    pipe: Any,
    result: Any,
    *,
    plan_res: Any,
    needs_tool: bool,
    task_id: Any,
    tid: str,
    write_progress: Callable[..., None],
) -> str:
    from core.bench_guardian import is_frozen
    from core.pipeline import StageResult
    from core.schemas import Envelope, GrandidieriteRequest

    tool_block = ""
    if not (needs_tool and plan_res is not None and plan_res.payload.tool_request):
        return tool_block
    t1 = time.perf_counter()
    treq = dict(plan_res.payload.tool_request)
    action = str(treq.get("action") or "generate")
    write_progress(tid, result.objective, "extend", action)
    if action == "run":
        try:
            from gems.grandidierite.registry import run_tool

            name = str(treq.get("name") or "")
            payload = treq.get("payload") or {}
            tr = run_tool(name, payload)
            tool_block = str(tr)[:2000]
            result.tool_output_chars = len(tool_block)
            result.stages.append(
                StageResult(
                    stage="tool_run",
                    success=bool(tr.get("ok")),
                    detail=name,
                    duration_ms=(time.perf_counter() - t1) * 1000,
                )
            )
        except Exception as e:
            result.stages.append(
                StageResult(
                    stage="tool_run",
                    success=False,
                    detail=str(e)[:120],
                    duration_ms=(time.perf_counter() - t1) * 1000,
                )
            )
        return tool_block
    if action in ("generate", "fabricate") and is_frozen():
        result.stages.append(
            StageResult(
                stage="extend",
                success=False,
                detail="blocked_by_bench_guardian",
                duration_ms=(time.perf_counter() - t1) * 1000,
            )
        )
        return tool_block
    g_req = Envelope(
        task_id=task_id,
        target_gem="grandidierite",
        payload=GrandidieriteRequest(tool_request=treq),
    )
    g_res = pipe.registry.execute(g_req)
    result.stages.append(
        StageResult(
            stage="extend",
            success=not bool(g_res.error),
            detail=action,
            duration_ms=(time.perf_counter() - t1) * 1000,
        )
    )
    return tool_block
