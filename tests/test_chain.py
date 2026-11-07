"""One gem's result is the next gem's input."""
from __future__ import annotations

from pathlib import Path

from core.agent.gems import chain


def test_a_shell_stops_at_security(tmp_path: Path) -> None:
    row = chain(tmp_path, "import subprocess")
    assert row["note"] == "blocked"
    assert row["security"] == "stop"


def test_prose_stops_at_profile(tmp_path: Path) -> None:
    row = chain(tmp_path, "I think")
    assert row["note"] == "no shape"
    assert row["profile"] == "ask"


def test_a_function_reaches_evolve(tmp_path: Path) -> None:
    row = chain(tmp_path, "def add(a, b):\n    return a + b", "search")
    assert row["ok"] is True
    assert "evolve" in row
