"""p2 leftover: agent-loop path + generate_fn live off Pipeline.run."""
from __future__ import annotations

import inspect

from core.loop.agent_loop_path import run_agent_loop_path
from core.loop.generate_fn import agent_loop_enabled, make_generate_fn
from core.pipeline import Pipeline


def test_pipeline_run_calls_agent_loop_path() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "run_agent_loop_path" in src
    assert "ETHER_LOOP_SECONDS" not in src


def test_generate_fn_delegates() -> None:
    src = inspect.getsource(Pipeline._make_generate_fn)
    assert "make_generate_fn" in src
    assert "rose_complete" not in src
    assert callable(make_generate_fn)
    assert callable(agent_loop_enabled)
    assert callable(run_agent_loop_path)
    assert Pipeline()._agent_loop_enabled() is agent_loop_enabled()
