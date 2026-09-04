"""Single-consumer coordination. One 4B on one 4GB card. Not a swarm.

phase4_swarm_plan writes spawned=False on purpose. This module is the lock so
a later PR cannot "upgrade" that into process spawn without failing FAST tests.
"""
from __future__ import annotations

from typing import Any, Dict

MAX_LIVE_AGENTS = 1
SPAWNED = False


def assert_single_consumer(plan: Dict[str, Any]) -> None:
    if plan.get("spawned"):
        raise AssertionError("swarm spawn is forbidden on this host")
    if plan.get("gpu"):
        raise AssertionError("swarm GPU fan-out is forbidden on this host")
    agents = plan.get("agents") or []
    live = [a for a in agents if a.get("live")]
    if live:
        raise AssertionError(f"swarm agents marked live: {live}")
    if MAX_LIVE_AGENTS != 1:
        raise AssertionError("MAX_LIVE_AGENTS is the 4B identity")
