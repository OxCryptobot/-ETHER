"""goal skill FAST: living gate met, leftover named, fix objectives use DAG."""
from __future__ import annotations

from core.loop.goal import LIVING_GATE, classify_objective, current


def test_living_gate_met() -> None:
    g = current()
    assert g["living_gate"]["met"] is True
    assert LIVING_GATE["merge"] == 3
    assert LIVING_GATE["ledger"] == 3
    assert g["swarm"] is False
    assert g["max_live_agents"] == 1
    assert "lora_train_12gb" in g["leftover"]


def test_fix_objective_uses_dag() -> None:
    c = classify_objective("fix ledger unaided")
    assert c["kind"] == "fix_dag"
    assert c["uses_fix_dag"] is True


def test_goal_objective() -> None:
    c = classify_objective("what is the goal leftover")
    assert c["kind"] == "goal"
