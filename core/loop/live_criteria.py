"""Unaided LIVE criteria. Same rule as merge/ledger gate. Expansion fixtures inherit it."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

POLICY = "model"
REQUIRED_TOOLS: Tuple[str, ...] = ("bug_comments", "replace_once", "run_tests")
FORBIDDEN_POLICY: Tuple[str, ...] = ("teacher_playbook", "craft_helper")
GATE = {"merge": 3, "ledger": 3}
EXPAND: Tuple[str, ...] = ("lru", "topo", "intervals")
ORACLE = "pytest repo_oracle"


def unaided_pass(row: Dict[str, Any]) -> bool:
    """One LIVE run counts iff policy=model, pytest passed, and the 4B edited."""
    policy = str(row.get("policy") or "")
    if policy != POLICY:
        return False
    if any(bad in policy for bad in FORBIDDEN_POLICY):
        return False
    if row.get("ok") is not True:
        return False
    if float(row.get("score") or 0) < 1.0:
        return False
    tools = [str(t) for t in (row.get("tools") or [])]
    if "replace_once" not in tools:
        return False
    if "run_tests" not in tools:
        return False
    if "bug_comments" not in tools:
        return False
    return True


def gate_met(counts: Dict[str, int]) -> bool:
    return all(int(counts.get(name) or 0) >= need for name, need in GATE.items())


def expansion_left(passed: Iterable[str]) -> Tuple[str, ...]:
    have = set(passed)
    return tuple(name for name in EXPAND if name not in have)
