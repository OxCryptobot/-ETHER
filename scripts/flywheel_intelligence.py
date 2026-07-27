"""Helpers: curriculum objective + verified promote + guardian + auto-enqueue."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple


def resolve_objective(cli_objective: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """Always prefer curriculum. CLI objective only if curriculum disabled."""
    meta: Dict[str, Any] = {}
    if os.getenv("ETHER_CURRICULUM", "1") == "1":
        try:
            from core.curriculum import sample_objective
            from core.autonomy import ensure_assert_objective

            item = sample_objective()
            meta = {
                "curriculum_id": item.get("id"),
                "curriculum_tier": item.get("tier"),
                "curriculum_tier_name": item.get("tier_name"),
                "curriculum_title": item.get("title"),
                "curriculum_source": item.get("source"),
                # Carried alongside the objective, never appended to it — the
                # generator must not see what it will be graded on.
                "holdout_test": item.get("holdout_test") or "",
            }
            obj = ensure_assert_objective(str(item.get("objective") or "print(1)"))
            return obj, meta
        except Exception as e:
            meta = {"curriculum_error": str(e)[:120]}
    # fallback still assert-bearing
    try:
        from core.autonomy import ensure_assert_objective

        obj = ensure_assert_objective(cli_objective or "")
    except Exception:
        obj = cli_objective or (
            "Write only Python with asserts:\n"
            "def is_even(n):\n    return n % 2 == 0\n"
            "assert is_even(4) is True\n"
            "assert is_even(5) is False\n"
            "print('ok')\n"
        )
    return obj, meta


def after_agentic(
    success: bool,
    task_id: str = "",
    verification_score: float = 0.0,
    total_tests: int = 0,
    objective: str = "",
    fail_kind: str = "runtime",
    stderr: str = "",
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if os.getenv("ETHER_CURRICULUM", "1") == "1":
        try:
            from core.curriculum import record_outcome

            out["curriculum_state"] = record_outcome(
                success,
                task_id=task_id,
                verification_score=verification_score,
                total_tests=total_tests,
            )
        except Exception as e:
            out["curriculum_error"] = str(e)[:120]
    try:
        from core.bench_guardian import evaluate

        out["guardian"] = evaluate()
    except Exception as e:
        out["guardian_error"] = str(e)[:120]
    try:
        from core.health_metric import declare_healthy

        out["healthy"] = declare_healthy()
    except Exception as e:
        out["healthy_error"] = str(e)[:120]

    # Autonomy: requeue failures + keep batch fed
    try:
        from core.autonomy import on_pipeline_outcome

        out["autonomy"] = on_pipeline_outcome(
            success=success,
            objective=objective,
            task_id=task_id,
            verification_score=verification_score,
            total_tests=total_tests,
            fail_kind=fail_kind,
            stderr=stderr,
        )
    except Exception as e:
        out["autonomy_error"] = str(e)[:120]
    return out
