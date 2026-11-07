"""The ReAct loop routes a stage to a gem. Theatre is skipped."""
from __future__ import annotations

from core.agent.gems import live, route_stage


def test_a_live_gem_is_routed() -> None:
    row = route_stage("sandbox")
    assert row["ok"] is True
    assert row["gem"] == "clear_quartz"
    assert row["writes"] is False


def test_a_theatre_gem_is_skipped() -> None:
    row = route_stage("plan")
    assert row["ok"] is False
    assert row["reason"] == "theatre"


def test_only_live_gems_run() -> None:
    assert live() == ["clear_quartz"]


def test_memory_stores_the_trace(tmp_path) -> None:
    from core.agent.gems import memory
    from core.agent.sota import recall

    row = memory(tmp_path, "search fits")
    assert row["ok"] is True
    assert row["gem"] == "citrine"
    assert "search" in recall(tmp_path)
