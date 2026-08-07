"""Phase 1 — ruff gate unit tests (no ruff binary required for skip path)."""
from pathlib import Path

from core.ruff_gate import ruff_gate_enabled, run_ruff


def test_ruff_gate_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ETHER_RUFF_GATE", raising=False)
    assert ruff_gate_enabled() is False


def test_ruff_gate_enabled(monkeypatch):
    monkeypatch.setenv("ETHER_RUFF_GATE", "1")
    assert ruff_gate_enabled() is True


def test_run_ruff_empty_paths():
    r = run_ruff([])
    assert r["ok"] is True
    assert r.get("skipped") is True
