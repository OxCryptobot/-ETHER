from scripts.live_status import write, MAX_AGE_H

def test_live_status_marks_stale_sept12() -> None:
    row = write()
    assert row.get("stale") is True
    assert row.get("live") is False
    assert float(row.get("max_age_hours") or 0) == MAX_AGE_H
    assert (row.get("age_hours") or 0) > MAX_AGE_H
