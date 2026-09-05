"""Upgrade FAST: flywheel lessons from traces, canned tools, pack names, MCP fallback."""
from __future__ import annotations

from core.loop.canned_tools import CANNED, fabricate_canned
from core.loop.flywheel import daily_scoreboard, lesson_from_trace, last_lessons, prepend_lessons
from core.loop.living import FIXTURES
from core.loop.mcp_tests import run_tests_mcp


def test_lesson_from_trace_not_playbook(tmp_path, monkeypatch) -> None:
    from core.loop import flywheel as fw

    monkeypatch.setattr(fw, "LESSONS", tmp_path / "lessons.jsonl")
    row = lesson_from_trace({"tools": ["list_files", "replace_once", "run_tests"], "ok": True})
    assert row["playbook"] is False
    assert "run_tests" in row["text"] or row["needs_run_tests"] is False
    assert last_lessons(1)[0]["kind"] == "trace"


def test_prepend_lessons(tmp_path, monkeypatch) -> None:
    from core.loop import flywheel as fw

    monkeypatch.setattr(fw, "LESSONS", tmp_path / "lessons.jsonl")
    lesson_from_trace({"tools": ["replace_once"], "ok": False})
    out = prepend_lessons("fix ledger")
    assert out.startswith("Prior lessons:")
    assert "fix ledger" in out


def test_daily_scoreboard_tape() -> None:
    board = daily_scoreboard(
        [
            {"ok": True, "seconds": 10, "tools": ["run_tests"]},
            {"ok": False, "seconds": 20, "tools": ["list_files"]},
        ]
    )
    assert board["n"] == 2
    assert board["ok"] == 1
    assert "unaided" in board["tape"]


def test_canned_five_names() -> None:
    assert len(CANNED) == 5
    names = {n for n, _ in CANNED}
    assert "echo_tool" in names
    assert "pytest_runner" in names


def test_fabricate_canned_stub() -> None:
    rows = fabricate_canned()
    assert len(rows) == 5
    assert all(r.get("promoted") is False for r in rows)


def test_pack_plus_names_exist() -> None:
    for name in ("merge", "ledger", "lru", "topo", "intervals"):
        assert name in FIXTURES


def test_mcp_tests_fallback() -> None:
    out = run_tests_mcp(code="def test_ok():\n    assert True\n")
    assert "via" in out
    assert "ok" in out
