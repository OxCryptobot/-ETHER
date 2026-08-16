"""Phase 3 controlled-evolution measurement package."""
from __future__ import annotations


def test_phase3_canaries():
    from core.phase3_canaries import run_matrix

    out = run_matrix()
    assert out.get("ok") is True, out
    assert out.get("soft_launch_blocked") is True


def test_phase3_status():
    from core.phase3_status import compute

    out = compute()
    assert out.get("phase") == "3"
    assert out.get("soft_launch_blocked") is True
    assert out.get("lora_train_blocked") is True
    assert out.get("training_wheels") is True
    assert isinstance(out.get("locked"), list)
    assert len(out.get("locked") or []) >= 3


def test_agent_state_and_lora_doctrine():
    from core.agent_state import AgentState
    from core.lora_dry_tick import dry_tick

    s = AgentState(thread_id="t3_doctrine")
    s.training_wheels = True
    s.save()
    assert AgentState.load("t3_doctrine") is not None
    d = dry_tick(force=True)
    assert d.get("trained") is False
    assert d.get("dry_run") is True
