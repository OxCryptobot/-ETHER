"""p2 leftover: skip_detail names resume skips."""
from __future__ import annotations

import inspect

from core.loop.stage_mark import skip_detail
from core.pipeline import Pipeline


def test_skip_detail() -> None:
    assert skip_detail(set(), "sandbox") == ""
    assert skip_detail({"sandbox"}, "sandbox") == "skipped_resume"
    assert skip_detail({"sandbox"}, "audit") == ""
    assert skip_detail({"audit"}, "audit") == "skipped_resume"


def test_pipeline_uses_skip_detail() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "skip_detail" in src
