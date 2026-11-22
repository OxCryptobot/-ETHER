"""Honest PASS gate. Generate-fallback is never product success."""
from __future__ import annotations
from typing import Any, Dict

GENERATE_STRATEGIES = frozenset({"repair_heavy", "generate", "best_of_n", "agent_loop", "resample"})


def is_honest_tool_path_pass(result: Dict[str, Any]) -> bool:
    if not result.get("ok"):
        return False
    if result.get("generate_fallback") or result.get("fallback") == "generate":
        return False
    degraded = result.get("degraded") or []
    for d in degraded:
        s = str(d).lower()
        if "tool_runtime_fallback" in s or "tool_runtime_failed_terminal" in s:
            return False
        if "generate" in s and "fallback" in s:
            return False
    strategy = str(result.get("strategy") or result.get("path") or "").lower()
    if strategy in GENERATE_STRATEGIES:
        return False
    tools = result.get("tools") or result.get("tool_names") or []
    steps = result.get("steps") or []
    if not tools and not steps and not result.get("tool_runtime_ok"):
        return False
    if result.get("tests_ok") is False:
        return False
    return True


def reject_generate_pass(result: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(result)
    if not is_honest_tool_path_pass(row):
        row["ok"] = False
        row["honest"] = False
        row.setdefault("reason", "generate_or_unverified_not_pass")
    else:
        row["honest"] = True
    return row
