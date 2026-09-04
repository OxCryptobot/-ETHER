"""Labradorite reads tool traces, not playbooks."""
from __future__ import annotations

from typing import Any, Dict, List


def last_tool_trace(scoreboard: Dict[str, Any]) -> List[str]:
    tools = scoreboard.get("tools")
    if isinstance(tools, list) and tools:
        return [str(t) for t in tools]
    results = scoreboard.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        inner = results[0].get("tools")
        if isinstance(inner, list) and inner:
            return [str(t) for t in inner]
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


def labradorite_from_trace(scoreboard: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 4: profiler from the tool tape. Never a teacher playbook."""
    tools = last_tool_trace(scoreboard)
    return {
        "ok": True,
        "source": "trace",
        "playbook": False,
        "tools": tools,
        "critique": critique_from_trace(tools),
        "needs_run_tests": "run_tests" not in tools,
        "needs_mutate": "replace_once" not in tools,
    }
