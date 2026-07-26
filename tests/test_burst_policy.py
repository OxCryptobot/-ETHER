"""Burst is specialist-only."""

from __future__ import annotations

from core.burst_policy import should_force_burst, burst_enabled


def test_burst_disabled(monkeypatch):
    monkeypatch.setenv("ETHER_BURST", "0")
    assert burst_enabled() is False
    assert should_force_burst(attempt=2, strategy="default") is False


def test_burst_on_retry(monkeypatch):
    monkeypatch.setenv("ETHER_BURST", "1")
    monkeypatch.setenv("ETHER_BURST_ON_FAIL", "1")
    assert should_force_burst(attempt=1, strategy="default") is False
    assert should_force_burst(attempt=2, strategy="default") is True


def test_burst_hard_tag(monkeypatch):
    monkeypatch.setenv("ETHER_BURST", "1")
    assert should_force_burst(attempt=1, strategy="default", hard_tag=True) is True
    assert should_force_burst(attempt=1, strategy="default", objective="[HARD] refactor") is True
