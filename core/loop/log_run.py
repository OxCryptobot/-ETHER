"""Amethyst log peeled off Pipeline._log. learn stays False on this path."""
from __future__ import annotations

from typing import Any

from core.schemas import AmethystRequest, Envelope


def log_run(pipe: Any, result: Any, learn: bool = False) -> None:
    try:
        pipe.registry.execute(
            Envelope(
                task_id=result.task_id,
                target_gem="amethyst",
                payload=AmethystRequest(
                    action="log",
                    interaction={
                        "task_id": str(result.task_id),
                        "objective": result.objective,
                        "status": result.status,
                        "confidence": result.confidence,
                        "execution_score": result.execution_score,
                        "verification_score": result.verification_score,
                        "retries": result.retries,
                        "strategy": result.strategy,
                        "strategies": list(result.strategies),
                        "reward": result.reward,
                        "used_burst": result.used_burst,
                        "first_compile_ok": result.first_compile_ok,
                        "plan_ok": result.plan_ok,
                        "experience_chars": result.experience_chars,
                        "exit_code": result.sandbox.exit_code if result.sandbox else None,
                        "audit_approved": bool(result.audit and result.audit.approved),
                        "error": result.error,
                        "learn": learn,
                    },
                ),
            )
        )
    except Exception:
        pass
