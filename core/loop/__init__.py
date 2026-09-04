"""Loop runner — thin stage dispatcher for the extracted Pipeline.run stages."""

import os

from core.loop.stages import TOOL_FIRST_ORDER, LEGACY_GENERATE_ORDER
from core.loop.tool_first import decide_tool_first_terminal


def loop_runner_enabled() -> bool:
    """Strangler flag: ETHER_LOOP_RUNNER default-on. Set 0 to disable. Routes extracted stages via LoopRunner."""
    return os.getenv("ETHER_LOOP_RUNNER", "1") == "1"


__all__ = [
    "loop_runner_enabled",
    "decide_tool_first_terminal",
    "TOOL_FIRST_ORDER",
    "LEGACY_GENERATE_ORDER",
    "fix_plan",
    "walk_fix",
]


def __getattr__(name: str):
    if name in {"fix_plan", "walk_fix"}:
        from core.loop.fix_dag import fix_plan, walk_fix

        return fix_plan if name == "fix_plan" else walk_fix
    raise AttributeError(name)
