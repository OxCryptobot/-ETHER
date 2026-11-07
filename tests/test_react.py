"""The ReAct loop runs a tool and writes the observation back."""
from __future__ import annotations

from pathlib import Path

from core.agent.react import react


def test_a_tool_reply_is_used(tmp_path: Path) -> None:
    core = tmp_path / "core" / "kernel"
    core.mkdir(parents=True)
    (core / "budget.py").write_text("def fits(text: str) -> bool:\n    return True\n", encoding="utf-8")
    replies = iter([
        '{"tool": "search", "args": {"query": "fits"}}',
        "def fits_name() -> str:\n    return 'fits'",
    ])
    row = react(lambda *_a, **_k: next(replies), tmp_path, "find fits", turns=3)
    assert row["used"] is True
    assert "def fits_name" in row["text"]


def test_a_repeat_stops(tmp_path: Path) -> None:
    same = '{"tool": "search", "args": {"query": "fits"}}'
    row = react(lambda *_a, **_k: same, tmp_path, "find fits", turns=3)
    assert row.get("note") == "repeat"
