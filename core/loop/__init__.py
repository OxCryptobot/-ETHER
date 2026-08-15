"""Loop runner — thin stage dispatcher for the extracted Pipeline.run stages."""

import os

from core.loop.stages import TOOL_FIRST_ORDER, LEGACY_GENERATE_ORDER
from core.loop.tool_first import decide_tool_first_terminal


def loop_runner_enabled() -> bool:
    """Strangler flag: ETHER_LOOP_RUNNER=1 routes extracted stages via LoopRunner."""
    return os.getenv("ETHER_LOOP_RUNNER", "0") == "1"


__all__ = [
    "loop_runner_enabled",
    "decide_tool_first_terminal",
    "TOOL_FIRST_ORDER",
    "LEGACY_GENERATE_ORDER",
]
