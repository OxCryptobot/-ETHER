"""Push hygiene surface on measure_tick + moonshots."""
from __future__ import annotations


def test_push_hygiene_compute():
    from core.push_hygiene import compute

    out = compute()
    assert out.get("gitignore_has_log") is True
    assert out.get("github_limit_mb") == 100
    assert "log_bytes" in out


def test_moonshots_has_hygiene_tile():
    from dashboard.collector_moonshots import collect_moonshots

    m = collect_moonshots()
    ids = {t["id"] for t in m.get("tiles") or []}
    assert "push_hygiene" in ids
