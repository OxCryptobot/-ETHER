"""Finalize handler — the extracted tail of Pipeline.run (legacy lines 827-938).

Strangler-fig stage 1: when ETHER_LOOP_RUNNER=1, Pipeline.run routes the
finalize tail through FinalizeHandler instead of the inline legacy block
(`Pipeline._finalize_legacy`). Behavior is byte-identical by construction;
scripts/shadow_runner.py proves it scenario by scenario.

Boundary rules (topology D2): stdlib, pydantic, core.schemas, core.fail_streak,
core.experience, core.bench_guardian, core.patterns only. No gems.* imports —
the grandidierite bridge is injected as `run_tool`. Never imports core.pipeline:
stages leave here as StageResult-shaped dicts and the caller constructs them.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from core.bench_guardian import is_frozen
from core.experience import record as experience_record
from core.fail_streak import maybe_propose_fabricate, record_outcome
from core.patterns import index_pass_pattern
from core.schemas import Envelope, GrandidieriteRequest


class FinalizeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str  # str(result.task_id)
    objective: str
    generated: str = ""  # generated or ""
    success: bool  # exit_code == 0
    last_err: str = ""
    fail_kind: str = ""
    strategy: str
    confidence: float
    verification_score: float
    total_tests: int
    holdout_ok: Optional[bool]
    holdout_test: str = ""
    tool_assist: bool
    has_sandbox: bool  # result.sandbox is not None
    exit_code: Optional[int]
    result_error: Optional[str] = None  # result.error at tail entry


class FinalizeOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str  # "complete" | "error"
    error: Optional[str] = None  # None => leave result.error unchanged
    stages: List[Dict[str, Any]]  # StageResult-shaped dicts (no core.pipeline here)
    degraded: List[str]  # appended to result.degraded by the caller


class FinalizeHandler:
    """Runs the finalize tail against injected boundaries."""

    def __init__(self, registry: Any, run_tool: Callable[..., Dict[str, Any]]):
        self._registry = registry
        self._run_tool = run_tool

    def run(self, ctx: FinalizeContext) -> FinalizeOutcome:
        stages: List[Dict[str, Any]] = []
        degraded: List[str] = []

        record_outcome(
            ctx.success, error=None if ctx.success else (ctx.last_err or ctx.result_error)
        )

        try:
            experience_record(
                objective=ctx.objective,
                code=ctx.generated,
                success=ctx.success,
                confidence=ctx.confidence,
                strategy=ctx.strategy,
                stderr=ctx.last_err if not ctx.success else "",
                fail_kind=ctx.fail_kind if not ctx.success else "",
                task_id=ctx.task_id,
                verification_score=ctx.verification_score,
                total_tests=ctx.total_tests,
                holdout_ok=ctx.holdout_ok,
                holdout_test=ctx.holdout_test,
            )
        except Exception as e:
            # A-3: was a silent except:pass — a run that lost its experience
            # record looked identical to one that kept it.
            degraded.append(f"experience_record_failed:{type(e).__name__}")

        if not ctx.success:
            proposal = maybe_propose_fabricate()
            if proposal and not is_frozen():
                t_fab = time.perf_counter()
                fab_req = Envelope(
                    task_id=UUID(ctx.task_id),
                    target_gem="grandidierite",
                    payload=GrandidieriteRequest(tool_request=proposal),
                )
                fab_res = self._registry.execute(fab_req)
                stages.append(
                    {
                        "stage": "auto_fabricate",
                        "success": not bool(fab_res.error),
                        "detail": proposal.get("name", ""),
                        "duration_ms": (time.perf_counter() - t_fab) * 1000,
                    }
                )
            elif proposal and is_frozen():
                stages.append(
                    {
                        "stage": "auto_fabricate",
                        "success": False,
                        "detail": "blocked_by_bench_guardian",
                    }
                )

        if ctx.success and ctx.generated and ctx.tool_assist:
            try:
                self._run_tool(
                    "save_success_pattern",
                    {
                        "objective": ctx.objective,
                        "code": ctx.generated,
                        "confidence": ctx.confidence,
                        "tags": [ctx.strategy],
                        # So the writer can refuse an artifact that carries
                        # the holdout. Without this the store re-injects
                        # leaked-era code into every later prompt.
                        "holdout_test": ctx.holdout_test,
                    },
                )
                cit = index_pass_pattern(
                    objective=ctx.objective,
                    code=ctx.generated,
                    confidence=ctx.confidence,
                    strategy=ctx.strategy,
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
                stages.append({"stage": "memory_save", "success": cit_ok, "detail": detail})
            except Exception as e:
                # A bare `pass` here removed the row entirely, so a crash
                # in this block looked identical to the stage never running.
                stages.append(
                    {
                        "stage": "memory_save",
                        "success": False,
                        "detail": f"memory_save failed: {str(e)[:200]}",
                    }
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
        error: Optional[str] = None
        if ctx.has_sandbox and ctx.exit_code == 0:
            status = "complete"
        else:
            status = "error"
            if not ctx.result_error:
                detail = (ctx.last_err or "").strip()
                error = f"sandbox exit {ctx.exit_code}" + (f": {detail[:500]}" if detail else "")

        return FinalizeOutcome(status=status, error=error, stages=stages, degraded=degraded)
