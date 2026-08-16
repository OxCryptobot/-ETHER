"""1D timeout retirement: expanded seed + projected rate."""
from __future__ import annotations


def test_seed_covers_diagnosis_fixtures():
    from core.live_fixture_policy import SEED_DENY, should_skip_live

    for name in ("ledger", "lru", "topo", "intervals"):
        assert name in SEED_DENY
        d = should_skip_live(fixture=name)
        assert d["skip"] is True, name


def test_job_id_with_lru_denied():
    from core.live_fixture_policy import should_skip_live

    d = should_skip_live(job={"id": "ss_pipeline_lru_live_001", "class": "live"})
    assert d["skip"] is True


def test_retirement_has_projected():
    from core.timeout_retirement import compute

    out = compute()
    assert "projected" in out
    proj = out["projected"]
    assert "projected_timeout_rate" in proj or proj.get("live_n_adj") is not None
    assert out.get("target_rate") == 0.25
    # wheels doctrine: high rate => keep_wheels_on
    if out.get("timeout_rate") is not None and out["timeout_rate"] >= 0.25:
        assert "keep_wheels_on" in (out.get("actions") or [])
