"""The loop searches, edits, tests, and a checker reads the result."""
from __future__ import annotations

from pathlib import Path

from core.agent.checker import check
from core.agent.skills import list_skills, route


def test_search_finds_the_file(tmp_path: Path) -> None:
    core = tmp_path / "core" / "kernel"
    core.mkdir(parents=True)
    (core / "budget.py").write_text("def packed_count(text: str) -> int:\n    return 0\n", encoding="utf-8")
    row = route(tmp_path, "search", query="packed_count")
    assert row["ok"] is True
    assert row["hits"][0] == "core/kernel/budget.py"


def test_edit_and_test_are_skills(tmp_path: Path) -> None:
    names = list_skills()
    assert "edit" in names
    assert "test" in names
    row = route(tmp_path, "edit", rel="missing.py", old="a", new="b")
    assert row["ok"] is False


def test_the_checker_cannot_write(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "sota.json").write_text(
        '{"goals": ["same_count"], "last": {"file": "core/kernel/context_budget.py", "kept": true}}',
        encoding="utf-8",
    )
    row = check(tmp_path, "same_count")
    assert row["ok"] is True
    assert row["writes"] is False
    assert row["gem"] == "checker"
