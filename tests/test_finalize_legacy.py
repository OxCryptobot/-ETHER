"""p2 leftover: finalize tail lives in finalize_legacy, not inline in Pipeline."""
from __future__ import annotations

import inspect

from core.loop.finalize_legacy import finalize_legacy
from core.pipeline import Pipeline


def test_pipeline_finalize_delegates() -> None:
    src = inspect.getsource(Pipeline._finalize_legacy)
    assert "finalize_legacy" in src
    assert "save_success_pattern" not in src


def test_finalize_legacy_named() -> None:
    assert callable(finalize_legacy)
    sig = inspect.signature(finalize_legacy)
    assert "tool_assist" in sig.parameters
    assert "exit_code" in sig.parameters
