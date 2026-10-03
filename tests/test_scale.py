"""Repeatable honest edits open a read-only second look. Nothing else writes source."""
import json
from pathlib import Path

from core.kernel.scale import advance, check


def _edit(root: Path, ts: str, honest: bool) -> None:
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "live_edit_tx.json").write_text(json.dumps({
        "ts": ts,
        "honest": honest,
        "ok": honest,
        "tests_ok": honest,
        "tools": ["replace_once"],
    }), encoding="utf-8")


def test_checker_never_writes_source(tmp_path: Path) -> None:
    src = tmp_path / "add.py"
    src.write_text("return a - b\n", encoding="utf-8")
    _edit(tmp_path, "t1", True)
    row = advance(tmp_path)
    assert src.read_text(encoding="utf-8") == "return a - b\n"
    assert row["checker"]["writes"] == 0
    assert check({"honest": True, "tests_ok": True})["ok"] is True


def test_one_pass_does_not_open_a_second_worker(tmp_path: Path) -> None:
    _edit(tmp_path, "t1", True)
    row = advance(tmp_path)
    assert row["repeatable"] is False
    assert row["second_look"]["worker"] == "closed"
    assert row["second_look"]["stream"] is False
    assert row["second_look"]["cross_repo"] is False


def test_two_honest_timestamps_open_a_read_only_look(tmp_path: Path) -> None:
    _edit(tmp_path, "t1", True)
    advance(tmp_path)
    _edit(tmp_path, "t2", True)
    row = advance(tmp_path)
    assert row["repeatable"] is True
    assert row["second_look"]["open"] is True
    assert row["second_look"]["writes"] == 0
    assert row["second_look"]["worker"] == "read_only"


def test_a_failed_edit_does_not_count(tmp_path: Path) -> None:
    _edit(tmp_path, "t1", False)
    row = advance(tmp_path)
    assert row["honest"] is False
    assert row["checker"]["skipped"] is True
    assert row["second_look"]["n"] == 0
