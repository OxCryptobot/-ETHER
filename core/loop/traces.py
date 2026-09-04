"""Labradorite reads tool traces, not playbooks."""
from __future__ import annotations

from typing import Any, Dict, List


def last_tool_trace(scoreboard: Dict[str, Any]) -> List[str]:
    tools = scoreboard.get("tools")
    if isinstance(tools, list):
        return [str(t) for t in tools]
    steps = scoreboard.get("steps")
    if isinstance(steps, list):
        names = []
        for step in steps:
            if isinstance(step, dict) and step.get("tool"):
                names.append(str(step["tool"]))
            elif isinstance(step, str):
                names.append(step)
        return names
    return []


def critique_from_trace(tools: List[str]) -> str:
    if not tools:
        return "no trace"
    if "run_tests" not in tools:
        return "trace missing run_tests after mutate"
    return "trace has " + " -> ".join(tools[-8:])
