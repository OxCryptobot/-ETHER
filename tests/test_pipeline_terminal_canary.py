"""Phase 2A terminal canary — pure parity, adapter OFF."""
from __future__ import annotations


def test_terminal_canary_matrix_all_pass():
    from core.pipeline_terminal_canary import run_matrix

    out = run_matrix()
    assert out.get("ok") is True, out
    assert out.get("passed") == out.get("n")
    assert out.get("adapter_enabled") is False


def test_adapter_default_off_still():
    from core.pipeline_adapter import terminal_adapter_enabled

    assert terminal_adapter_enabled() is False
