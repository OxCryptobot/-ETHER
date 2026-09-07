"""p2 leftover: generate/repair while-loop lives off Pipeline.run."""
from __future__ import annotations

import inspect

from core.loop.generate_retry_loop import run_generate_retry_loop
from core.pipeline import Pipeline


def test_pipeline_run_calls_generate_retry_loop() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "run_generate_retry_loop" in src
    assert "while attempt < max_attempts" not in src


def test_generate_retry_loop_named() -> None:
    assert callable(run_generate_retry_loop)
    sig = inspect.signature(run_generate_retry_loop)
    assert "st" in sig.parameters
    assert "write_progress" in sig.parameters
