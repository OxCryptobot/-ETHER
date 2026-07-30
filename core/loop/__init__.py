"""Loop runner — thin stage dispatcher for the extracted Pipeline.run stages."""

import os


def loop_runner_enabled() -> bool:
    """Strangler flag: ETHER_LOOP_RUNNER=1 routes extracted stages via LoopRunner."""
    return os.getenv("ETHER_LOOP_RUNNER", "0") == "1"
