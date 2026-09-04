"""p4_02 FAST: Labradorite reads traces, never a teacher playbook."""
from __future__ import annotations

from core.loop.traces import critique_from_trace, labradorite_from_trace, last_tool_trace


def test_extracts_tools_from_scoreboard() -> None:
    tools = last_tool_trace(
        {"tools": ["list_files", "bug_comments", "replace_once", "run_tests"]}
    )
    assert tools[-1] == "run_tests"


def test_missing_run_tests_is_named() -> None:
    text = critique_from_trace(["list_files", "replace_once"])
    assert "run_tests" in text


def test_labradorite_from_trace_not_playbook() -> None:
    out = labradorite_from_trace(
        {
            "results": [
                {
                    "tools": ["list_files", "replace_once", "run_tests"],
                    "ok": True,
                }
            ]
        }
    )
    assert out["playbook"] is False
    assert out["source"] == "trace"
    assert "playbook" not in out["critique"].lower()
    assert out["needs_run_tests"] is False


def test_empty_trace() -> None:
    out = labradorite_from_trace({})
    assert out["playbook"] is False
    assert out["needs_run_tests"] is True
