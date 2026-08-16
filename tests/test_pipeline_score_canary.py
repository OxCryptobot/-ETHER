"""Phase 2A score canary."""
from __future__ import annotations


def test_score_canary_all_pass():
    from core.pipeline_score_canary import run_matrix

    out = run_matrix()
    assert out.get("ok") is True, out
    assert out.get("adapter_enabled") is False
