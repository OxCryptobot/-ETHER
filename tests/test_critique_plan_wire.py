"""Phase 1D — critique plan wire + dashboard latency honesty."""
from __future__ import annotations


def test_critique_plan_wire_runs():
    from core.critique_plan_wire import wire_latest

    out = wire_latest()
    assert "n_critiques" in out
    assert "n_replanned" in out
    assert out.get("training_wheels") is True
    assert out.get("path")


def test_plan_from_budget_exhaust_replans():
    from core.plan_state import plan_from_failure

    p = plan_from_failure(
        objective="ss_direct_hard timeout",
        failure_type="budget_exhaust",
        training_wheels=True,
    )
    assert p.get("replan") is True
    assert "max_steps" in (p.get("hypothesis") or "").lower() or "cap" in (
        p.get("hypothesis") or ""
    ).lower()


def test_moonshots_include_1d_tiles():
    from dashboard.collector_moonshots import collect_moonshots

    m = collect_moonshots()
    ids = {t["id"] for t in m["tiles"]}
    assert "latency_slo" in ids
    assert "live_timeout" in ids
    assert "live_budget" in ids
    assert "plan_wire" in ids
    assert len(m["tiles"]) >= 12
