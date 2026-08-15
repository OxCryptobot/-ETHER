"""Tool-first terminal decision — pure function over ToolRuntimeGateHandler.

Pipeline may call decide_tool_first_terminal() instead of inlining degrade
markers. Behavior matches ToolRuntimeGateHandler exactly.
"""
from __future__ import annotations

from typing import List

from core.loop.handlers.tool_runtime_gate import (
    ToolRuntimeGateContext,
    ToolRuntimeGateHandler,
    ToolRuntimeGateOutcome,
)


def decide_tool_first_terminal(
    *,
    enabled: bool,
    done_ok: bool,
    score: float = 0.0,
    error: str = "",
    degraded: List[str] | None = None,
) -> ToolRuntimeGateOutcome:
    """Return terminal gate outcome for tool-runtime path.

    enabled=False → not terminal (legacy generate may continue)
    enabled=True and done_ok → terminal PASS
    enabled=True and not done_ok → terminal FAIL (tool_runtime_failed_terminal)
    """
    return ToolRuntimeGateHandler().run(
        ToolRuntimeGateContext(
            tool_runtime_enabled=enabled,
            tool_runtime_ok=done_ok,
            tool_runtime_score=float(score or 0.0),
            tool_runtime_error=error or "",
            degraded=list(degraded or []),
        )
    )
