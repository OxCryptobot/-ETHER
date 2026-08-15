"""Phase 2 PlanState unit tests."""
from __future__ import annotations

from core.plan_state import PlanState, plan_from_failure


def test_observe_fail_lowers_confidence_and_replans():
    ps = PlanState(objective="fix ledger", confidence=0.7, training_wheels=True)
    ps.observe_fail("no_progress", note="stagnant")
    assert ps.confidence < 0.7
    assert ps.should_replan() is True
    out = ps.replan()
    assert out["replan"] is True
    assert "hypothesis" in out
    assert out["confidence"] <= 0.55


def test_plan_from_failure_timeout():
    out = plan_from_failure(objective="live ledger", failure_type="timeout")
    assert out["ok"] is True
    assert out["replan"] is True
    assert "scripted" in out["hypothesis"].lower() or "budget" in out["hypothesis"].lower() or "scope" in out["hypothesis"].lower()


def test_pass_raises_confidence():
    ps = PlanState(confidence=0.4)
    ps.observe_pass("green")
    assert ps.confidence > 0.4
    assert ps.last_failure_type is None
