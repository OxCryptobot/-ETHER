"""The next goal uses a function that already passed."""
from __future__ import annotations

import pytest

from pathlib import Path

from core.agent.learn import batch_size, next_from, score



@pytest.fixture(autouse=True)
def _legacy_ladder(monkeypatch):
    """These tests pin the legacy ladder (retired by default in batch 2)."""
    monkeypatch.setenv("ETHER_SOTA_LEGACY", "1")
    monkeypatch.setenv("ETHER_GOAL_SOURCE", "0")

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
    done = {"same_count", "within_budget"}
    nxt = next_from(tmp_path, done)
    assert nxt is not None
    assert nxt["id"] == "count_diff"
    found = next_from(tmp_path, done | {"count_diff", "room_left"})
    assert found is not None
    assert found["id"] == "find_fits"
    assert "file" not in found["test"] or "fits_name" in found["test"]


def test_the_batch_grows_after_success(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "sota.json").write_text('{"goals": ["a"], "kept_n": 5, "last": {"kept": true}}', encoding="utf-8")
    assert batch_size(tmp_path) == 8
    (art / "sota.json").write_text('{"goals": [], "kept_n": 0}', encoding="utf-8")
    assert batch_size(tmp_path) == 3
