"""Agentic contract. ETHER is a local-first AGENTIC coding agent.

Not Best-of-N generate (ETHER_AGENT_LOOP). That loop measured net-negative.
The living agentic cycle is Observe → tool → sandbox → critique → memory.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from core.loop.live_criteria import unaided_pass

STAGES: Tuple[str, ...] = (
    "observe",
    "tool",
    "sandbox",
    "critique",
    "memory",
)
POLICY = "model"
FORBIDDEN = ("teacher_playbook", "craft_helper", "generate_fallback")


def is_agentic_pass(row: Dict[str, Any]) -> bool:
    """A run is agentic PASS only on the unaided tool path."""
    if not unaided_pass(row):
        return False
    tools = [str(t) for t in (row.get("tools") or [])]
    if "generate" in tools and "replace_once" not in tools:
        return False
    return True


def classify_cycle(row: Dict[str, Any]) -> str:
    policy = str(row.get("policy") or "")
    if policy in FORBIDDEN:
        return "not_agentic"
    if is_agentic_pass(row):
        return "agentic_pass"
    if row.get("ok") is True:
        return "ok_not_agentic"
    return "agentic_fail"
