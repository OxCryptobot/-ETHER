"""p2 leftover: plan execute + close_run live off Pipeline.run."""
from __future__ import annotations

import inspect

from core.loop.close_run import close_run
from core.loop.execute_plan import execute_selenite_plan
from core.pipeline import Pipeline


def test_pipeline_run_calls_execute_and_close() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "execute_selenite_plan" in src
    assert "close_run" in src
    assert "SeleniteRequest" not in src
    assert "FinalizeContext" not in src


def test_named_entries() -> None:
    assert callable(execute_selenite_plan)
    assert callable(close_run)
