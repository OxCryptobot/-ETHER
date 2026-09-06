"""Legacy finalize tail peeled off Pipeline._finalize_legacy."""
from __future__ import annotations

import time
from typing import Any, Optional

from core.bench_guardian import is_frozen
from core.experience import record as experience_record
from core.fail_streak import maybe_propose_fabricate, record_outcome
from core.patterns import index_pass_pattern
from core.schemas import Envelope, GrandidieriteRequest

def finalize_legacy(
    registry: Any,
    result: Any,
    *,
    objective: str,
    generated: str,
    last_err: str,
    fail_kind: str,
    strategy: str,
    total_tests: int,
    holdout_test: str,
    tool_assist: bool,
    exit_code: Optional[int],
) -> None:
    """Pre-extraction finalize tail (default path). Byte-identical behavior
    to the pre-refactor inline block; removed when ETHER_LOOP_RUNNER
    defaults on (roadmap stage 6)."""
    from core.pipeline import StageResult

    task_id = result.task_id
    tid = str(task_id)
    success = exit_code == 0
    record_outcome(success, error=None if success else (last_err or result.error))

    try:
        experience_record(
            objective=objective,
            code=generated or "",
            success=success,
            confidence=result.confidence,
            strategy=strategy,
            stderr=last_err if not success else "",
            fail_kind=fail_kind if not success else "",
            task_id=tid,
            verification_score=result.verification_score,
            total_tests=total_tests,
            holdout_ok=result.holdout_ok,
            holdout_test=holdout_test,
        )
    except Exception as e:
        # A-3: was a silent pass — a run that lost its experience record
        # looked identical to one that kept it. The loop-runner handler
        # emits the identical string for this seam.
        result.degraded.append(f"experience_record_failed:{type(e).__name__}")

    if not success:
        proposal = maybe_propose_fabricate()
        if proposal and not is_frozen():
            t_fab = time.perf_counter()
            fab_req = Envelope(
                task_id=task_id,
                target_gem="grandidierite",
                payload=GrandidieriteRequest(tool_request=proposal),
            )
            fab_res = registry.execute(fab_req)
            result.stages.append(
                StageResult(
                    stage="auto_fabricate",
                    success=not bool(fab_res.error),
                    detail=proposal.get("name", ""),
                    duration_ms=(time.perf_counter() - t_fab) * 1000,
                )
            )
        elif proposal and is_frozen():
            result.stages.append(
                StageResult(
                    stage="auto_fabricate",
                    success=False,
                    detail="blocked_by_bench_guardian",
                )
            )

    if success and generated and tool_assist:
        try:
            from gems.grandidierite.registry import run_tool

            run_tool(
                "save_success_pattern",
                {
                    "objective": objective,
                    "code": generated,
                    "confidence": result.confidence,
                    "tags": [strategy],
                    # So the writer can refuse an artifact that carries
                    # the holdout. Without this the store re-injects
                    # leaked-era code into every later prompt.
                    "holdout_test": holdout_test,
                },
            )
            cit = index_pass_pattern(
                objective=objective,
                code=generated,
                confidence=result.confidence,
                strategy=strategy,
            )
            # success must be DERIVED, not asserted. This was hardcoded
            # True while the real citrine error was demoted to a
            # substring of the detail line — which is how a memory
            # layer that had never once stored a pattern kept
            # reporting a green stage.
            cit_ok = bool(cit.get("ok"))
            detail = f"success_pattern citrine={cit_ok}"
            if not cit_ok and cit.get("error"):
                detail += f" error={str(cit['error'])[:200]}"
            result.stages.append(
                StageResult(stage="memory_save", success=cit_ok, detail=detail)
            )
        except Exception as e:
            # A bare `pass` here removed the row entirely, so a crash
            # in this block looked identical to the stage never running.
            result.stages.append(
                StageResult(
                    stage="memory_save",
                    success=False,
                    detail=f"memory_save failed: {str(e)[:200]}",
                )
            )

    # Status is DERIVED from the sandbox, not asserted. This was an
    # unconditional "complete", so a run whose generated code never once
    # executed successfully still reported complete — and cli/main.py
    # (`Exit(0 if result.status == "complete" else 1)`) therefore exited
    # 0 on a total failure, while dashboard/collector.py counted it in
    # `runs_complete` and pinned pipeline_success_rate at 1.0.
    # "error" (not a third value) is deliberate: it is the vocabulary
    # _fail() and orchestrator.Status already use, so the existing
    # complete/error buckets stay exhaustive.
    # Phase B: repo_oracle_ok=False forces error even on sandbox exit=0.
    if result.repo_oracle_ok is False:
        result.status = "error"
        if not result.error:
            detail = (last_err or "").strip()
            result.error = "repo_oracle failed" + (f": {detail[:500]}" if detail else "")
    elif result.sandbox is not None and result.sandbox.exit_code == 0:
        result.status = "complete"
    else:
        result.status = "error"
        if not result.error:
            detail = (last_err or "").strip()
            result.error = f"sandbox exit {exit_code}" + (f": {detail[:500]}" if detail else "")

