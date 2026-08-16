"""Timeout diagnosis contracts."""
from __future__ import annotations


def test_timeout_diagnosis_runs():
    from core.timeout_diagnosis import compute

    out = compute()
    assert "live_n" in out
    assert "timeout_n" in out
    assert "timeout_rate" in out or out.get("live_n") == 0
    assert "top_fixtures" in out
    assert out.get("path")
    assert out.get("target_rate") == 0.25


def test_is_timeout_floor():
    from core.timeout_diagnosis import _is_timeout

    assert _is_timeout({"duration_s": 300, "failure_type": "timeout"}, {"ok": False}) is True
    assert _is_timeout({"duration_s": 2}, {"ok": True, "timeout": False}) is False
