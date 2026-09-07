"""p2 leftover: checkpoint shadow lives off Pipeline.run (I-010)."""
from __future__ import annotations

import inspect

from core.loop.shadow_progress import make_write_progress
from core.pipeline import Pipeline


def test_pipeline_run_uses_shadow_progress() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "make_write_progress" in src
    assert "checkpoint_pipeline" not in src


def test_make_write_progress_named() -> None:
    assert callable(make_write_progress)
