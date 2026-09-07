"""Bounded walks on expand fixtures. policy=craft_helper. Not unaided LIVE."""
from __future__ import annotations

from core.loop.live_criteria import expansion_left, unaided_pass
from core.loop.walk_fixture import walk_bounded


def test_walk_bounded_topo() -> None:
    out = walk_bounded("topo", timeout=45)
    assert out["ok"] is True
    assert out["policy"] == "craft_helper"
    assert out["gate_count"] is False


def test_walk_bounded_intervals() -> None:
    out = walk_bounded("intervals", timeout=45)
    assert out["ok"] is True
    assert out["policy"] == "craft_helper"
    assert out["gate_count"] is False


def test_expand_left_and_unaided() -> None:
    left = expansion_left(("topo",))
    assert "lru" in left
    assert "intervals" in left
    assert unaided_pass({"policy": "craft_helper", "ok": True, "score": 1.0, "tools": ["bug_comments", "replace_once", "run_tests"]}) is False
