"""Phase 1 critical packages — eligible KPIs + local host health."""
from __future__ import annotations


def test_eligible_rates_separates_raw_and_eligible():
    from core.eligible_rates import compute

    out = compute()
    assert "timeout_rate_raw" in out
    assert "timeout_rate_eligible" in out
    assert "honest_rate_eligible" in out
    assert out.get("soft_launch_blocked") is True
    assert out.get("wheels_must_stay_on") is True
    assert isinstance(out.get("denied"), list)
    # denied fixtures must shrink eligible vs raw when history has ledger timeouts
    if out.get("live_raw_n", 0) > 0 and out.get("denied_live_n", 0) > 0:
        assert out["live_eligible_n"] <= out["live_raw_n"]


def test_host_health_no_git_flag():
    from core.host_health import compute

    out = compute()
    assert out.get("git_required") is False
    assert "alive" in out
    assert "age_s" in out or out.get("heartbeat") is None


def test_moonshots_eligible_tile_optional():
    """Collector should not crash; eligible tile preferred."""
    from dashboard.collector_moonshots import collect_moonshots

    m = collect_moonshots()
    assert "tiles" in m
