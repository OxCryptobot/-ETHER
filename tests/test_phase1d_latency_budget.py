"""Phase 1D — latency honesty + live budget. Behavior-preserving."""
from __future__ import annotations


def test_latency_slo_has_timeout_split():
    from core.latency_slo import compute

    data = compute()
    assert "scripted" in data
    assert "live" in data
    assert "live_completed" in data
    assert "live_timeout" in data
    assert "live_timeout_rate" in data
    assert "timeout_floor_s" in data
    assert data["timeout_floor_s"] >= 60
    # alert field always present
    assert "alert" in data


def test_live_budget_defaults_tight():
    from core.live_budget import limits, apply_to_job, publish

    lim = limits()
    assert lim["max_wall_s"] <= 120
    assert lim["max_steps"] <= 16
    assert lim["step_timeout_s"] <= 40
    assert lim["training_wheels"] is True or lim["training_wheels"] is False

    job = {
        "id": "t_live",
        "class": "live",
        "note": "pipeline live ledger",
        "steps": [{"argv": ["x"], "timeout": 900}],
    }
    clamped = apply_to_job(job)
    assert clamped["steps"][0]["timeout"] <= lim["max_wall_s"]
    assert "live_budget" in clamped

    # non-live unchanged
    fast = {"id": "t_fast", "class": "fast", "steps": [{"argv": ["y"], "timeout": 180}]}
    assert apply_to_job(fast)["steps"][0]["timeout"] == 180

    pub = publish()
    assert pub.get("path")


def test_live_budget_does_not_lift_wheels():
    from core.live_budget import limits

    lim = limits()
    # module never auto-enables live enqueue while wheels default on
    if lim["training_wheels"]:
        assert lim["live_enqueue_allowed"] is False
