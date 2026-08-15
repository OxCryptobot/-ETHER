"""Tool-runtime gate stage (LoopRunner extraction slice).

Encodes the terminal harden contract outside pipeline.py narrative:
  - If tool_runtime is enabled and does not finish ok → terminal failure
  - Do NOT fall through to generate as a silent "success path" for 1D gates

Pipeline may still call generate for other modes; measurement of tool-path
lift must treat tool_runtime_failed_terminal as FAIL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolRuntimeGateContext:
    tool_runtime_enabled: bool
    tool_runtime_ok: bool
    tool_runtime_score: float = 0.0
    tool_runtime_error: str = ""
    degraded: List[str] = field(default_factory=list)


@dataclass
class ToolRuntimeGateOutcome:
    terminal: bool
    ok: bool
    reason: str
    degraded: List[str] = field(default_factory=list)
    score: float = 0.0


class ToolRuntimeGateHandler:
    """Decide terminal vs continue after tool_runtime stage."""

    def run(self, ctx: ToolRuntimeGateContext) -> ToolRuntimeGateOutcome:
        if not ctx.tool_runtime_enabled:
            return ToolRuntimeGateOutcome(
                terminal=False,
                ok=True,
                reason="tool_runtime_disabled",
                degraded=list(ctx.degraded),
                score=ctx.tool_runtime_score,
            )
        if ctx.tool_runtime_ok:
            return ToolRuntimeGateOutcome(
                terminal=True,
                ok=True,
                reason="tool_runtime_ok",
                score=ctx.tool_runtime_score,
            )
        degraded = list(ctx.degraded)
        if "tool_runtime_failed_terminal" not in degraded:
            degraded.append("tool_runtime_failed_terminal")
        return ToolRuntimeGateOutcome(
            terminal=True,
            ok=False,
            reason=ctx.tool_runtime_error or "tool_runtime_failed_terminal",
            degraded=degraded,
            score=ctx.tool_runtime_score,
        )


def is_honest_tool_path_pass(result: Dict[str, Any]) -> bool:
    """Scoreboard helper: ok only if not a generate-fallback disguise."""
    if not result.get("ok"):
        return False
    degraded = result.get("degraded") or []
    for d in degraded:
        s = str(d).lower()
        if "tool_runtime_fallback" in s or "tool_runtime_failed_terminal" in s:
            return False
    strategy = str(result.get("strategy") or "").lower()
    if strategy in ("repair_heavy", "generate", "best_of_n"):
        # Live generate path is not Phase-1 tool-path lift
        if result.get("mode") == "live":
            return False
    return True
