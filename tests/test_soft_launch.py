"""Phase 3.3 — soft launch never auto-greens."""
from __future__ import annotations

import os

from core.soft_launch import evaluate


def test_missing_rates_blocks(monkeypatch):
    monkeypatch.delenv("ETHER_SOFT_LAUNCH", raising=False)
    monkeypatch.setenv("ETHER_TRAINING_WHEELS", "1")
    out = evaluate(rates={})
    assert out["soft_launch_ready"] is False
    assert out["soft_launch_blocked"] is True
    assert "no_live_rows" in out["blocked_reasons"] or "no_honest_live_rates_artifact" in out[
        "blocked_reasons"
    ]


def test_green_rates_still_blocked_without_flag(monkeypatch):
    monkeypatch.delenv("ETHER_SOFT_LAUNCH", raising=False)
    monkeypatch.setenv("ETHER_TRAINING_WHEELS", "0")
    rates = {
        "live_n": 10,
        "live_honest_rate": 1.0,
        "status": "honest_live_green",
    }
    out = evaluate(rates=rates)
    assert out["soft_launch_ready"] is False
    assert "ETHER_SOFT_LAUNCH_not_1" in out["blocked_reasons"]


def test_ready_only_with_all_gates(monkeypatch):
    monkeypatch.setenv("ETHER_SOFT_LAUNCH", "1")
    monkeypatch.setenv("ETHER_TRAINING_WHEELS", "0")
    rates = {
        "live_n": 5,
        "live_honest_rate": 0.99,
        "status": "honest_live_green",
    }
    out = evaluate(rates=rates, threshold=0.99)
    assert out["soft_launch_ready"] is True
    assert out["blocked_reasons"] == []


def test_pipeline_still_imports():
    from core.pipeline import Pipeline

    assert Pipeline is not None
