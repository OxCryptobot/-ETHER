"""Compose pure terminal decisions for future Pipeline wire.

Does not import or mutate Pipeline. Opt-in only when callers choose it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.pipeline_score import clamp_score, merge_degraded, terminal_ok_envelope
from core.pipeline_tool_first import decide_pipeline_tool_first


def decide_terminal(
    *,
    tool_runtime_enabled: bool,
    tool_runtime_done: bool,
    score: float = 0.0,
    degraded: Optional[List[str]] = None,
    error: str = "",
) -> Dict[str, Any]:
    """Single entry for tool-first terminal outcome + envelope."""
    d = decide_pipeline_tool_first(
        tool_runtime_enabled=tool_runtime_enabled,
        tool_runtime_done=tool_runtime_done,
        score=score,
        error=error,
        degraded=degraded,
    )
    if d.should_fail:
        return {
            "ok": False,
            "should_fail": True,
            "score": d.score,
            "stage": d.fail_stage,
            "marker": d.degrade_marker,
            "fail_msg": d.fail_msg,
            "reason": d.reason,
            "degraded": merge_degraded(
                (d.envelope or {}).get("degraded"), d.degrade_marker or ""
            ),
            "envelope": d.envelope,
        }
    env = terminal_ok_envelope(score=clamp_score(score), degraded=degraded)
    return {
        "ok": True,
        "should_fail": False,
        "score": env["score"],
        "stage": "",
        "marker": None,
        "fail_msg": "",
        "reason": d.reason,
        "degraded": env["degraded"],
        "envelope": env,
    }
