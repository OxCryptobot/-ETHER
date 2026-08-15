"""Pipeline tool-first terminal adapter — Phase 3.2.

Pure function mirroring the existing Pipeline terminal harden:
  if tool_first enabled and not done → FAIL with tool_runtime_failed_terminal
  else continue

Does not import Pipeline. Safe to unit-test. Wire into Pipeline.run only
behind a feature flag or after mentor sign-off so default path stays identical.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.loop.tool_first import decide_tool_first_terminal


@dataclass(frozen=True)
class ToolFirstDecision:
    should_fail: bool
    degrade_marker: Optional[str]
    fail_stage: str
    fail_msg: str
    reason: str


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
        return ToolFirstDecision(
            should_fail=True,
            degrade_marker="tool_runtime_failed_terminal",
            fail_stage="tool_runtime",
            fail_msg="tool_runtime_failed_terminal",
            reason=out.reason,
        )
    return ToolFirstDecision(
        should_fail=False,
        degrade_marker=None,
        fail_stage="",
        fail_msg="",
        reason=out.reason,
    )
