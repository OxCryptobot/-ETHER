"""FAIL → typed critique before a second hypothesis."""
from __future__ import annotations
from typing import Any, Dict

TAXONOMY = frozenset({"tool_order", "repair_quality", "parse_fail", "budget_exhaust", "trace_missing", "preference_pollution", "infra", "no_progress", "unknown"})

def valid_critique(row: Dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    cause = str(row.get("root_cause") or "")
    if cause not in TAXONOMY:
        return False
    if not str(row.get("evidence") or "").strip():
        return False
    if not str(row.get("smallest_experiment") or "").strip():
        return False
    try:
        conf = float(row.get("confidence") or 0)
    except (TypeError, ValueError):
        return False
    return 0.0 <= conf <= 1.0

def may_second_hypothesis(*, fail_is_infra: bool, critique: Dict[str, Any] | None) -> bool:
    if fail_is_infra:
        return False
    return valid_critique(critique)
