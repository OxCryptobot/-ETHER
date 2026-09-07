"""Bounded walks. policy=craft_helper. Not unaided. Host step budget 25s."""
from __future__ import annotations

from core.loop.live_criteria import unaided_pass
from core.loop.walk_fixture import walk_bounded


def test_walk_topo_policy() -> None:
    out = walk_bounded("topo", timeout=12)
    assert out.get("policy") == "craft_helper"
    assert out.get("gate_count") is False


def test_walk_intervals_policy() -> None:
    out = walk_bounded("intervals", timeout=12)
    assert out.get("policy") == "craft_helper"
    assert out.get("gate_count") is False


def test_craft_not_unaided() -> None:
    assert unaided_pass({"policy": "craft_helper", "ok": True, "score": 1.0, "tools": ["bug_comments", "replace_once", "run_tests"]}) is False
