"""Pipeline tool-first terminal adapter — Phase 3.2 + score slice.

Pure function. Does not import Pipeline. Uses pipeline_score for envelopes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.loop.tool_first import decide_tool_first_terminal
from core.pipeline_score import clamp_score, merge_degraded, terminal_fail_envelope


@dataclass(frozen=True)
class ToolFirstDecision:
    should_fail: bool
    degrade_marker: Optional[str]
    fail_stage: str
    fail_msg: str
    reason: str
    score: float = 0.0
    envelope: Optional[dict] = None


def decide_pipeline_tool_first(
    *,
    tool_runtime_enabled: bool,
    tool_runtime_done: bool,
    score: float = 0.0,
    error: str = "",
    degraded: Optional[List[str]] = None,
) -> ToolFirstDecision:
    """Return the same terminal contract Pipeline currently encodes inline."""
    out = decide_tool_first_terminal(
        enabled=tool_runtime_enabled,
        done_ok=tool_runtime_done,
        score=score,
        error=error,
        degraded=list(degraded or []),
    )
    if tool_runtime_enabled and not tool_runtime_done:
        env = terminal_fail_envelope(
            stage="tool_runtime",
            marker="tool_runtime_failed_terminal",
            score=clamp_score(score),
            msg="tool_runtime_failed_terminal",
            degraded=merge_degraded(degraded, "tool_runtime_failed_terminal"),
        )
        return ToolFirstDecision(
            should_fail=True,
            degrade_marker="tool_runtime_failed_terminal",
            fail_stage="tool_runtime",
            fail_msg="tool_runtime_failed_terminal",
            reason=out.reason,
            score=env["score"],
            envelope=env,
        )
    return ToolFirstDecision(
        should_fail=False,
        degrade_marker=None,
        fail_stage="",
        fail_msg="",
        reason=out.reason,
        score=clamp_score(score),
        envelope=None,
    )
