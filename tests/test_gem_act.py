"""A gem decision changes the outcome."""
from __future__ import annotations

from pathlib import Path

from core.agent.react import react


def test_a_shell_is_blocked(tmp_path: Path) -> None:
    text = '{"tool": "search", "args": {"query": "os.system(\'rm\')"}}'
    row = react(lambda *_a, **_k: text, tmp_path, "find", turns=2)
    assert row.get("note") == "blocked"


def test_an_unknown_tool_stops(tmp_path: Path) -> None:
    text = '{"tool": "nope", "args": {}}'
    row = react(lambda *_a, **_k: text, tmp_path, "find", turns=2)
    assert row.get("note") == "unknown tool"
