"""The agent picks a skill. Unknown names fail closed."""
from __future__ import annotations

from pathlib import Path

from core.agent.skills import list_skills, route


def test_search_finds_a_symbol(tmp_path: Path) -> None:
    core = tmp_path / "core" / "kernel"
    core.mkdir(parents=True)
    (core / "budget.py").write_text("def packed_count(text: str) -> int:\n    return 0\n", encoding="utf-8")
    row = route(tmp_path, "search", query="packed_count")
    assert row["ok"] is True
    assert "core/kernel/budget.py" in row["hits"]


def test_an_unknown_skill_fails_closed(tmp_path: Path) -> None:
    row = route(tmp_path, "shell")
    assert row["ok"] is False
    assert row["reason"] == "unknown"
    assert "search" in list_skills()
