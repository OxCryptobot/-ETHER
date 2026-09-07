"""few-shot / experience + lazy repo-map/context. Peeled off Pipeline.run."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Tuple


def load_retrieval(
    result: Any,
    *,
    objective: str,
    tool_assist: bool,
    tid: str,
    write_progress: Callable[..., None],
) -> Tuple[str, str]:
    from core.experience import retrieve as experience_retrieve
    from core.pipeline import StageResult

    few_shot = ""
    exp_block = ""
    if not tool_assist:
        return few_shot, exp_block
    t_ta = time.perf_counter()
    write_progress(tid, objective, "tool_assist")
    try:
        from gems.grandidierite.registry import run_tool

        fs = run_tool("few_shot_pack", {"query": objective, "top_k": 2})
        if fs.get("ok") and isinstance(fs.get("result"), dict):
            few_shot = fs["result"].get("block") or ""
        exp = experience_retrieve(objective, k=3)
        exp_block = exp.get("block") or ""
        result.stages.append(
            StageResult(
                stage="tool_assist",
                success=True,
                detail=f"few_shot={len(few_shot)}c exp={len(exp_block)}c",
                duration_ms=(time.perf_counter() - t_ta) * 1000,
            )
        )
    except Exception as e:
        result.stages.append(
            StageResult(
                stage="tool_assist",
                success=False,
                detail=str(e)[:120],
                duration_ms=(time.perf_counter() - t_ta) * 1000,
            )
        )
    return few_shot, exp_block


def make_lazy_blocks(
    pipe: Any,
    result: Any,
    *,
    tool_assist: bool,
    tid: str,
    objective: str,
    write_progress: Callable[..., None],
) -> Tuple[Callable[[], str], Callable[[], str]]:
    lazy: Dict[str, str] = {}

    def repo_map_block() -> str:
        if "repo_map" not in lazy:
            lazy["repo_map"] = pipe._fetch_repo_map(result) if tool_assist else ""
        return lazy["repo_map"]

    def workspace_block() -> str:
        if "context" not in lazy:
            write_progress(tid, objective, "context")
            lazy["context"] = pipe._fetch_context(result, objective)
        return lazy["context"]

    return repo_map_block, workspace_block
