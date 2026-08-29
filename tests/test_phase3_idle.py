"""Idle hook stays dry and never soft-launches."""
from __future__ import annotations


def test_idle_tick_shape():
    from core.phase3_idle import idle_tick

    out = idle_tick()
    assert out.get("soft_launch") is False
    assert "ok" in out
