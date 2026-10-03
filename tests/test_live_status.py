from datetime import datetime, timezone

from scripts.live_status import MAX_AGE_H, judge, write


def test_not_today_is_stale() -> None:
    row = judge(
        "2026-09-12T00:00:00+00:00",
        True,
        now=datetime(2026, 10, 3, tzinfo=timezone.utc),
    )
    assert row["stale"] is True
    assert row["live"] is False
    assert row["age_hours"] > MAX_AGE_H
    assert row["same_utc_day"] is False


def test_today_and_young_can_be_live() -> None:
    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    row = judge("2026-10-03T11:00:00+00:00", True, now=now)
    assert row["stale"] is False
    assert row["live"] is True


def test_write_uses_the_same_rule() -> None:
    row = write()
    assert float(row.get("max_age_hours") or 0) == MAX_AGE_H
    assert "stale" in row and "live" in row
