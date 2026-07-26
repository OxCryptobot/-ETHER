"""Helpers: curriculum objective + guardian snapshot for flywheel."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple


def resolve_objective(cli_objective: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """Prefer curriculum sample when enabled."""
    meta: Dict[str, Any] = {}
    if os.getenv("ETHER_CURRICULUM", "1") == "1":
        try:
            from core.curriculum import sample_objective

            item = sample_objective()
            meta = {
                "curriculum_id": item.get("id"),
                "curriculum_tier": item.get("tier"),
                "curriculum_tier_name": item.get("tier_name"),
                "curriculum_title": item.get("title"),
            }
            return str(item.get("objective") or cli_objective or "print(1)"), meta
        except Exception as e:
            meta = {"curriculum_error": str(e)[:120]}
    obj = cli_objective or (
        "Write only this Python code with no markdown:\n"
        "def is_even(n):\n    return n % 2 == 0\n"
        "print(is_even(4))\nprint(is_even(5))\n"
    )
    return obj, meta


def after_agentic(success: bool, task_id: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if os.getenv("ETHER_CURRICULUM", "1") == "1":
        try:
            from core.curriculum import record_outcome

            out["curriculum_state"] = record_outcome(success, task_id=task_id)
        except Exception as e:
            out["curriculum_error"] = str(e)[:120]
    try:
        from core.bench_guardian import evaluate

        out["guardian"] = evaluate()
    except Exception as e:
        out["guardian_error"] = str(e)[:120]
    return out
