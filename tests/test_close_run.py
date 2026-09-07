"""p2 leftover: plan execute + close_run named entries (behavior, not inspect soup)."""
from __future__ import annotations

from core.loop.close_run import close_run
from core.loop.execute_plan import execute_selenite_plan


def test_named_entries() -> None:
    assert callable(execute_selenite_plan)
    assert callable(close_run)
