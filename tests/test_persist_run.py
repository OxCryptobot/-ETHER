"""p2 leftover: persist lives off Pipeline._persist."""
from __future__ import annotations

import inspect

from core.loop.persist_run import persist_run
from core.pipeline import Pipeline


def test_pipeline_persist_delegates() -> None:
    src = inspect.getsource(Pipeline._persist)
    assert "persist_run" in src
    assert "persist_failed" not in src
    assert callable(persist_run)
