"""Agent-loop path peeled off Pipeline.run (ETHER_AGENT_LOOP=1)."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional


def run_agent_loop_path(
    pipe: Any,
    result: Any,
    *,
    objective: str,
    task_id: Any,
    prefer_local: bool,
    holdout_test: str,
    generated: str,
) -> Dict[str, Any]:
    from core.loop.generate_fn import agent_loop_enabled, make_generate_fn
    from core.pipeline import StageResult

    loop_result = None
    max_attempts: Optional[int] = None
    if not agent_loop_enabled():
        return {
            "loop_result": None,
            "generated": generated,
            "max_attempts": None,
        }
    try:
        from core.agent_loop import LoopBudget, run_loop

        lt = time.perf_counter()
        loop_result = run_loop(
            objective,
            make_generate_fn(pipe, task_id, prefer_local),
            budget=LoopBudget(
                max_attempts=int(os.getenv("ETHER_LOOP_ATTEMPTS", "4")),
                wall_clock_s=float(os.getenv("ETHER_LOOP_SECONDS", "300")),
            ),
            holdout_test=holdout_test,
        )
        generated = loop_result.code or ""
        result.generated_code = generated
        result.strategy = "agent_loop"
        result.stages.append(
            StageResult(
                stage="agent_loop",
                success=bool(generated),
                detail=(
                    f"{len(loop_result.attempts)} candidates, "
                    f"best score {loop_result.score:.3f}, "
                    f"{loop_result.selection_reason}"
                )[:300],
                duration_ms=(time.perf_counter() - lt) * 1000,
            )
        )
        max_attempts = 1 if generated else 2
    except Exception as e:
        result.stages.append(
            StageResult(
                stage="agent_loop",
                success=False,
                detail=f"loop failed, falling back: {str(e)[:180]}",
            )
        )
        result.degraded.append(f"agent_loop_fallback:{type(e).__name__}")
        loop_result = None
    return {
        "loop_result": loop_result,
        "generated": generated,
        "max_attempts": max_attempts,
    }
