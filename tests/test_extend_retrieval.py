"""p2 leftover: extend + retrieval live off Pipeline.run."""
from __future__ import annotations

import inspect

from core.loop.extend_stage import run_extend_if_needed
from core.loop.retrieval import load_retrieval, make_lazy_blocks
from core.pipeline import Pipeline


def test_pipeline_run_calls_extend_retrieval() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "run_extend_if_needed" in src
    assert "load_retrieval" in src
    assert "make_lazy_blocks" in src
    assert "few_shot_pack" not in src
    assert "blocked_by_bench_guardian" not in src


def test_named_entries() -> None:
    assert callable(run_extend_if_needed)
    assert callable(load_retrieval)
    assert callable(make_lazy_blocks)
