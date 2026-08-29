"""Harden: flex_replace, replace_once, ast_outline, numbered boot."""
from __future__ import annotations

from pathlib import Path

from core.hard_live_tools import ast_outline, flex_replace
from core.tool_runtime import TOOL_SPECS, ToolRuntime

ROOT = Path(__file__).resolve().parents[1]
MERGE = ROOT / "fixtures" / "repo_oracle_merge"


def test_flex_replace_exact_and_stripped():
    body = "    return b  # BUG: should return list(b)\n"
    out, mode = flex_replace(body, "    return b  # BUG: should return list(b)", "    return list(b)")
    assert mode == "exact"
    assert "list(b)" in out
    out2, mode2 = flex_replace(body, "return b  # BUG: should return list(b)", "return list(b)")
    assert mode2 == "stripped-line"
    assert "return list(b)" in out2


def test_flex_replace_fail_closed_missing():
    try:
        flex_replace("abc\n", "nope", "x")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_ast_outline_finds_merge_sorted():
    text = (MERGE / "merge.py").read_text(encoding="utf-8")
    items = ast_outline(text)
    names = {i.get("name") for i in items}
    assert "merge_sorted" in names


def test_tool_specs_include_replace_once_and_ast_outline():
    names = {t["name"] for t in TOOL_SPECS}
    assert "replace_once" in names
    assert "ast_outline" in names


def test_replace_once_greens_one_merge_bug():
    plan = [
        {
            "tool": "replace_once",
            "args": {
                "path": "merge.py",
                "old": "return b  # BUG: should return list(b)",
                "new": "return list(b)",
            },
        },
        {"tool": "done", "args": {"reason": "one hyp"}},
    ]
    it = iter(plan)

    def decide(_m):
        try:
            return next(it)
        except StopIteration:
            return {"tool": "done", "args": {"reason": "stop"}}

    rt = ToolRuntime(fixture_root=MERGE, decide_fn=decide, max_steps=3, pytest_timeout=20)
    result = rt.run("one replace")
    assert result.steps[0].ok is True, result.steps[0].observation
    assert result.steps[0].observation.get("mutated") is True
