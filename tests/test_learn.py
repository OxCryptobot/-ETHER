"""The next goal uses a function that already passed."""
from __future__ import annotations

from pathlib import Path

from core.agent.learn import batch_size, next_from, score


def test_learning_composes_from_kept(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "sota.json").write_text(
        '{"goals": ["packed_count", "file_count", "fits", "is_over"]}',
        encoding="utf-8",
    )
    goal = next_from(tmp_path, set())
    assert goal is not None
    assert goal["id"] == "same_count"
    row = score(tmp_path)
    assert row["kept"] == 4
    assert row["learning"] is True


def test_the_batch_grows_after_success(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "sota.json").write_text('{"goals": ["a"], "kept_n": 5, "last": {"kept": true}}', encoding="utf-8")
    assert batch_size(tmp_path) == 8
    (art / "sota.json").write_text('{"goals": [], "kept_n": 0}', encoding="utf-8")
    assert batch_size(tmp_path) == 3
