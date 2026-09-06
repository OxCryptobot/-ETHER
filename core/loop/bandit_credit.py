"""Bandit credit peeled off Pipeline._credit_attempts / _policy_update."""
from __future__ import annotations

import inspect
from typing import Any, List


def credit_attempts(pipe: Any, attempts: List[Any], result: Any) -> None:
    from core.learning import compute_reward, learning_enabled

    if not learning_enabled():
        return
    pending = [a for a in attempts if not a.credited]
    if not pending:
        return
    interim = compute_reward(
        exit_code=1,
        confidence=0.0,
        audit_approved=False,
        retries=0,
        plan_ok=result.plan_ok,
    )
    for idx, rec in enumerate(pending):
        is_final = idx == len(pending) - 1
        rec.credited = True
        policy_update(
            pipe,
            rec,
            result.reward if is_final else interim,
            result,
            attempt=idx + 1,
            final=is_final,
        )


def policy_update(
    pipe: Any,
    rec: Any,
    reward: float,
    result: Any,
    attempt: int,
    final: bool,
) -> None:
    exit_code = (result.sandbox.exit_code if result.sandbox else None) if final else 1
    extra = {
        "task_id": str(result.task_id),
        "objective": result.objective[:300],
        "attempt": attempt,
        "final": final,
        "status": "complete" if exit_code == 0 else "error",
        "confidence": result.confidence if final else 0.0,
        "exit_code": exit_code,
        "audit_approved": bool(result.audit and result.audit.approved) if final else None,
    }
    try:
        params = inspect.signature(pipe.policy.update).parameters
        contextual = "context" in params or any(
            p.kind == p.VAR_KEYWORD for p in params.values()
        )
    except (TypeError, ValueError):
        contextual = False
    try:
        if contextual:
            pipe.policy.update(
                rec.strategy, reward, context=rec.context or None, extra=extra
            )
        else:
            pipe.policy.update(rec.strategy, reward)
    except Exception:
        pass
