"""Verify + finalize + persist + log. Peeled off Pipeline.run tail."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from core.loop import loop_runner_enabled
from core.loop.handlers.finalize import FinalizeContext
from core.loop.handlers.verify import VerificationContext
from core.loop.runner import LoopRunner
from core.progress import clear_progress
from core.schemas import BlackTourmalineResponse, LabradoriteResponse


def close_run(
    pipe: Any,
    result: Any,
    *,
    tid: str,
    objective: str,
    generated: str,
    tool_assist: bool,
    critique: bool,
    holdout_test: str,
    sent_prompts: List[str],
    skip: set,
    last_err: str,
    fail_kind: str,
    strategy: str,
    attempts: list,
    _tool_path_complete: bool,
) -> Any:
    from core.pipeline import StageResult

    if _tool_path_complete:
        exit_code = 0 if result.repo_oracle_ok else 1
        total_tests = (
            int(getattr(result.sandbox, "total_tests", 0) or 0) if result.sandbox else 0
        )
    elif loop_runner_enabled():
        _out = LoopRunner(registry=pipe.registry).run_verify(
            VerificationContext(
                task_id=tid,
                objective=objective,
                generated=generated or "",
                tool_assist=tool_assist,
                critique=critique,
                holdout_test=holdout_test,
                sent_prompts=sent_prompts,
                has_sandbox=result.sandbox is not None,
                sandbox_exit=result.sandbox.exit_code if result.sandbox else None,
                sandbox_total_tests=int(result.sandbox.total_tests)
                if result.sandbox
                else 0,
                confidence=result.confidence,
                verification_score=result.verification_score,
                retries=result.retries,
                plan_ok=result.plan_ok,
                first_compile_ok=result.first_compile_ok,
                used_burst=result.used_burst,
            )
        )
        for _s in _out.stages:
            result.stages.append(StageResult(**_s))
        result.confidence = _out.confidence
        if _out.audit is not None:
            result.audit = BlackTourmalineResponse.model_validate(_out.audit)
        if _out.critique is not None:
            result.critique = LabradoriteResponse.model_validate(_out.critique)
        result.holdout_ok = _out.holdout_ok
        result.reward = _out.reward
        exit_code, total_tests, holdout_test = (
            _out.exit_code,
            _out.total_tests,
            _out.holdout_test,
        )
    else:
        exit_code, total_tests, holdout_test = pipe._verify_legacy(
            result,
            objective=objective,
            generated=generated or "",
            critique=critique,
            holdout_test=holdout_test,
            sent_prompts=sent_prompts,
            tool_assist=tool_assist,
            skip=skip,
        )
    pipe._credit_attempts(attempts, result)

    if loop_runner_enabled():
        outcome = LoopRunner(registry=pipe.registry).run_finalize(
            FinalizeContext(
                task_id=tid,
                objective=objective,
                generated=generated or "",
                success=(exit_code == 0),
                last_err=last_err,
                fail_kind=fail_kind,
                strategy=strategy,
                confidence=result.confidence,
                verification_score=result.verification_score,
                total_tests=total_tests,
                holdout_ok=result.holdout_ok,
                holdout_test=holdout_test,
                tool_assist=tool_assist,
                has_sandbox=result.sandbox is not None,
                exit_code=exit_code,
                result_error=result.error,
            )
        )
        for _s in outcome.stages:
            result.stages.append(StageResult(**_s))
        result.degraded.extend(outcome.degraded)
        result.status = outcome.status
        if outcome.error is not None:
            result.error = outcome.error
    else:
        pipe._finalize_legacy(
            result,
            objective=objective,
            generated=generated or "",
            last_err=last_err,
            fail_kind=fail_kind,
            strategy=strategy,
            total_tests=total_tests,
            holdout_test=holdout_test,
            tool_assist=tool_assist,
            exit_code=exit_code,
        )
    result.finished_at = datetime.now(timezone.utc).isoformat()
    clear_progress()
    pipe._persist(result)
    pipe._log(result)
    return result
