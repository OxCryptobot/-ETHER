"""Gem topography: all eight names, walk does not crash."""
from __future__ import annotations

from core.loop.gem_topo import TOPO, walk_gems


def test_eight_gems() -> None:
    assert len(TOPO) == 8
    assert "selenite" in TOPO
    assert "grandidierite" in TOPO


def test_walk_gems_returns_eight() -> None:
    out = walk_gems("agentic ping")
    assert out["n"] == 8
    names = [r["gem"] for r in out["rows"]]
    assert names == TOPO
