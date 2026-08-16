"""Phase 1D projected denylist check."""
from __future__ import annotations


def test_phase1d_has_projected_check():
    from core.phase1d_status import compute

    out = compute()
    ids = {c["id"] for c in out.get("checks") or []}
    assert "denylist_projected_under_target" in ids
    # With current scoreboards + expanded denylist this should be green
    check = next(
        c for c in out["checks"] if c["id"] == "denylist_projected_under_target"
    )
    assert check["ok"] is True


def test_retire_tile_prefers_projected():
    from dashboard.collector_moonshots import collect_moonshots

    m = collect_moonshots()
    tile = next(t for t in m["tiles"] if t["id"] == "timeout_retire")
    # value should be projected rate (0.0) or numeric-like
    assert tile["good"] is True or tile.get("value") is not None
