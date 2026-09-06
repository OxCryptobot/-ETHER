"""p2 leftover: verify/audit spine lives in verify_legacy, not inline in Pipeline."""
from __future__ import annotations

import inspect

from core.loop.verify_legacy import verify_legacy
from core.pipeline import Pipeline


def test_pipeline_verify_delegates() -> None:
    src = inspect.getsource(Pipeline._verify_legacy)
    assert "verify_legacy" in src
    assert "secret_scan" not in src


def test_verify_legacy_named() -> None:
    assert callable(verify_legacy)
    sig = inspect.signature(verify_legacy)
    assert "skip" in sig.parameters
    assert "tool_assist" in sig.parameters
