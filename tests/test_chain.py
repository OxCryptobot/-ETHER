"""One gem's result is the next gem's input."""
from __future__ import annotations

from pathlib import Path

from core.agent.gems import chain


def test_a_shell_skips_route(tmp_path: Path) -> None:
    row = chain(tmp_path, "import subprocess")
    assert row["note"] == "blocked"
    assert row["route"] == "skip"


def test_a_tool_skips_profile(tmp_path: Path) -> None:
    row = chain(tmp_path, '{"tool": "search"}', "search")
    assert row["profile"] == "skip"
    assert row["ok"] is True


def test_a_function_reaches_evolve(tmp_path: Path) -> None:
    row = chain(tmp_path, "def add(a, b):\n    return a + b", "search")
    assert row["ok"] is True
    assert "evolve" in row
