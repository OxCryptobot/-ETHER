"""Build progress publisher."""
from __future__ import annotations


def test_build_progress_shape():
    from core.build_progress import compute

    out = compute()
    assert "overall_pct" in out
    assert "overall_bar" in out
    assert out.get("soft_launch") is False
    ids = {i["id"] for i in out.get("items") or []}
    assert "p1_metrics" in ids
    assert "hard_live" in ids
    assert "soft_launch" in ids
    assert out.get("path")
