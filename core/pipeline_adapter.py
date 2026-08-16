"""Flag-gated adapter between pure strangler slices and future Pipeline wire.

ETHER_PIPELINE_TERMINAL=1  → use core.pipeline_terminal.decide_terminal
Default 0                  → passthrough / no-op (behavior identical to today)

Never imports Pipeline. Never lifts training wheels.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def terminal_adapter_enabled() -> bool:
    return (os.getenv("ETHER_PIPELINE_TERMINAL") or "0").strip() == "1"


def maybe_decide_terminal(
    *,
    tool_runtime_enabled: bool,
    tool_runtime_done: bool,
    score: float = 0.0,
    degraded: Optional[List[str]] = None,
    error: str = "",
) -> Optional[Dict[str, Any]]:
    """Return terminal decision only when flag is on; else None (caller keeps legacy path)."""
    if not terminal_adapter_enabled():
        return None
    from core.pipeline_terminal import decide_terminal

    return decide_terminal(
        tool_runtime_enabled=tool_runtime_enabled,
        tool_runtime_done=tool_runtime_done,
        score=score,
        degraded=degraded,
        error=error,
    )


def status() -> Dict[str, Any]:
    return {
        "enabled": terminal_adapter_enabled(),
        "env": "ETHER_PIPELINE_TERMINAL",
        "default": "0",
        "note": "Default OFF. Pipeline.run not modified. Mentor must set flag to exercise path.",
    }
