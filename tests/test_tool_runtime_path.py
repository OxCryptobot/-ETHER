"""p2 leftover: tool-runtime path lives off Pipeline.run."""
from __future__ import annotations

import inspect

from core.loop.tool_runtime_path import run_tool_runtime_path
from core.pipeline import Pipeline


def test_pipeline_run_calls_tool_runtime_path() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "run_tool_runtime_path" in src
    assert "984s hang class" not in src


def test_run_tool_runtime_path_named() -> None:
    assert callable(run_tool_runtime_path)
    sig = inspect.signature(run_tool_runtime_path)
    assert "write_progress" in sig.parameters
    assert "timeout" in sig.parameters
