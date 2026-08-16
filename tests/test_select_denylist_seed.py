"""Select pure import + seeded LIVE denylist."""
from __future__ import annotations


def test_select_imports_pure_context():
    from core.pipeline_select import select_strategy

    s = select_strategy("simple objective")
    assert isinstance(s, str)


def test_ledger_seed_skips():
    from core.live_fixture_policy import should_skip_live, SEED_DENY

    assert "ledger" in SEED_DENY
    d = should_skip_live(job={"id": "ss_pipeline_ledger_live_001", "class": "live"})
    assert d["skip"] is True
    assert "ledger" in d["reason"]


def test_unknown_still_allowed():
    from core.live_fixture_policy import should_skip_live

    d = should_skip_live(fixture="green_scripted_ok_xyz")
    assert d["skip"] is False
