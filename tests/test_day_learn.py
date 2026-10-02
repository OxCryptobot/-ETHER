"""One real lesson per day. Timeouts are not lessons. Yesterday is kept."""
import json
from datetime import datetime, timezone
from pathlib import Path

from core.kernel.day_learn import learn


def _fail(root: Path, body: dict) -> None:
    dest = root / "artifacts" / "jobs" / "failed"
    dest.mkdir(parents=True)
    (dest / "edit.json").write_text(json.dumps(body), encoding="utf-8")


def test_one_lesson_per_day_and_it_is_preserved(tmp_path: Path) -> None:
    _fail(tmp_path, {"ok": False, "tail": "parse error in add.py", "job_id": "edit"})
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    first = learn(tmp_path, now)
    assert first["skipped"] is False
    assert first["lesson"]["root_cause"] == "parse_fail"
    assert first["thinking"]["kept"] is False
    second = learn(tmp_path, now)
    assert second["skipped"] is True
    assert second["preserved"]["root_cause"] == "parse_fail"
    text = (tmp_path / "artifacts" / "edit_memory.json").read_text(encoding="utf-8")
    assert "parse_fail" in text


def test_infra_failure_is_not_a_lesson(tmp_path: Path) -> None:
    _fail(tmp_path, {"ok": False, "error": "timeout", "tail": "Timeout"})
    row = learn(tmp_path, datetime(2026, 10, 3, tzinfo=timezone.utc))
    assert row["lesson"] is None
    assert row["thinking"] is None
