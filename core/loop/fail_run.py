"""Fail path peeled off Pipeline._fail."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional


def fail_run(
    pipe: Any,
    result: Any,
    stage: str,
    msg: str,
    t0: float,
    attempts: Optional[list] = None,
) -> Any:
    from core.bench_guardian import is_frozen
    from core.experience import record as experience_record
    from core.fail_streak import maybe_propose_fabricate, record_outcome
    from core.learning import compute_reward
    from core.pipeline import StageResult, _Attempt
    from core.progress import clear_progress
    from core.schemas import Envelope, GrandidieriteRequest

    result.status = "error"
    result.error = msg
    result.stages.append(
        StageResult(
            stage=stage,
            success=False,
            detail=msg,
            duration_ms=max(0.0, (time.perf_counter() - t0) * 1000),
        )
    )
    result.reward = compute_reward(
        exit_code=1,
        confidence=0.0,
        audit_approved=False,
        retries=result.retries,
        plan_ok=result.plan_ok,
        first_compile_ok=False,
        used_burst=result.used_burst,
    )
    if attempts is None and result.strategy:
        attempts = [_Attempt(strategy=result.strategy)]
    pipe._credit_attempts(attempts or [], result)
    try:
        experience_record(
            objective=result.objective,
            code=result.generated_code or "",
            success=False,
            confidence=0.0,
            strategy=result.strategy,
            stderr=msg,
            fail_kind=stage,
            task_id=str(result.task_id),
            verification_score=result.verification_score,
            total_tests=int(result.sandbox.total_tests) if result.sandbox else 0,
        )
    except Exception as e:
        result.degraded.append(f"experience_record_failed:{type(e).__name__}")
    try:
        record_outcome(False, error=msg)
        proposal = maybe_propose_fabricate()
        if proposal and not is_frozen():
            fab_res = pipe.registry.execute(
                Envelope(
                    task_id=result.task_id,
                    target_gem="grandidierite",
                    payload=GrandidieriteRequest(tool_request=proposal),
                )
            )
            fab_ok = not bool(fab_res.error)
            detail = proposal.get("name", "")
            if not fab_ok and fab_res.error:
                detail += f" — {str(fab_res.error.message)[:160]}"
            result.stages.append(
                StageResult(stage="auto_fabricate", success=fab_ok, detail=detail)
            )
    except Exception as e:
        result.degraded.append(f"auto_fabricate_failed:{type(e).__name__}")
    result.finished_at = datetime.now(timezone.utc).isoformat()
    clear_progress()
    pipe._persist(result)
    pipe._log(result)
    return result
