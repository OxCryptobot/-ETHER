"""Hard-LIVE tools: numbered read, edit_lines, bug_comments, merge/ledger scripted."""
from __future__ import annotations

from pathlib import Path

from core.hard_live_tools import (
    anchor_edit,
    edit_lines,
    extract_bug_comments,
    number_lines,
    observe_loop_hint,
    should_break_observe,
)
from core.tool_runtime import TOOL_SPECS, ToolRuntime

ROOT = Path(__file__).resolve().parents[1]
MERGE = ROOT / "fixtures" / "repo_oracle_merge"
LEDGER = ROOT / "fixtures" / "repo_oracle_ledger"


def test_number_lines_is_1_indexed():
    body = number_lines("alpha\nbeta\ngamma")
    assert "   1|alpha" in body
    assert "   2|beta" in body
    assert "   3|gamma" in body


def test_edit_lines_replaces_span():
    src = "a\nb\nc\nd\n"
    out = edit_lines(src, 2, 3, "X\nY")
    assert out.splitlines() == ["a", "X", "Y", "d"]


def test_edit_lines_bad_span_raises():
    try:
        edit_lines("a\nb\n", 2, 9, "z")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_anchor_edit_unique_line():
    body = "    b.credit(amount)\n    return s + s\n"
    out, line = anchor_edit(body, "return s + s", "    return s")
    assert line == 2
    assert "return s\n" in out
    assert "s + s" not in out


def test_bug_comments_find_merge_markers():
    hits = extract_bug_comments(MERGE)
    texts = " ".join(h["text"] for h in hits)
    assert hits
    assert "BUG" in texts
    assert any(h["path"].endswith("merge.py") for h in hits)


def test_observe_loop_breaks_at_three():
    assert should_break_observe(2) is False
    assert should_break_observe(3) is True
    hint = observe_loop_hint(3, ["merge.py"])
    assert "edit_lines" in hint
    assert "merge.py" in hint


def test_tool_specs_include_hard_live_tools():
    names = {t["name"] for t in TOOL_SPECS}
    assert "edit_lines" in names
    assert "bug_comments" in names


def test_numbered_read_file_output():
    def decide(_m):
        return {"tool": "read_file", "args": {"path": "merge.py"}}

    rt = ToolRuntime(fixture_root=MERGE, decide_fn=decide, max_steps=1, pytest_timeout=30)
    result = rt.run("read merge")
    obs = result.steps[0].observation
    assert result.steps[0].ok is True
    content = str(obs.get("content") or "")
    assert "|" in content
    assert obs.get("numbered") is True


def test_bug_comments_tool_on_merge():
    def decide(_m):
        return {"tool": "bug_comments", "args": {}}

    rt = ToolRuntime(fixture_root=MERGE, decide_fn=decide, max_steps=1, pytest_timeout=30)
    result = rt.run("bugs")
    obs = result.steps[0].observation
    assert result.steps[0].ok is True
    assert int(obs.get("n") or 0) >= 2


def _line(path: Path, needle: str) -> int:
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if needle in line:
            return i
    raise AssertionError(f"missing {needle!r} in {path}")


def test_scripted_edit_lines_fixes_merge():
    """Prove the new tool can green merge without a full write_file dump."""
    src = MERGE / "merge.py"
    lb = _line(src, "return b  # BUG")
    la = _line(src, "return a  # BUG")
    le = _line(src, "out.extend(a[i:])")
    plan = [
        {"tool": "bug_comments", "args": {}},
        {"tool": "read_file", "args": {"path": "merge.py"}},
        {
            "tool": "edit_lines",
            "args": {
                "path": "merge.py",
                "start_line": lb,
                "end_line": lb,
                "new": "        return list(b)",
            },
        },
        {
            "tool": "edit_lines",
            "args": {
                "path": "merge.py",
                "start_line": la,
                "end_line": la,
                "new": "        return list(a)",
            },
        },
        {
            "tool": "edit_lines",
            "args": {
                "path": "merge.py",
                "start_line": le,
                "end_line": le,
                "new": (
                    "        out.extend(a[i:])\n"
                    "    if j < len(b):\n"
                    "        out.extend(b[j:])"
                ),
            },
        },
        {"tool": "run_tests", "args": {}},
    ]
    it = iter(plan)

    def decide(_m):
        try:
            return next(it)
        except StopIteration:
            return {"tool": "done", "args": {"reason": "exhausted"}}

    rt = ToolRuntime(fixture_root=MERGE, decide_fn=decide, max_steps=8, pytest_timeout=30)
    result = rt.run("fix merge via edit_lines")
    assert result.ok is True, result.error or result.reason
    assert result.score == 1.0


def test_scripted_replace_once_fixes_ledger():
    """Do not use stacked edit_lines — inserts shift later spans (p1_245)."""
    plan = [
        {"tool": "bug_comments", "args": {}},
        {
            "tool": "anchor_edit",
            "args": {
                "path": "ledger.py",
                "contains": "b.credit(amount)",
                "new": "        a.debit(amount)\n        b.credit(amount)",
            },
        },
        {
            "tool": "replace_once",
            "args": {
                "path": "ledger.py",
                "old": "return s + s",
                "new": "return s",
            },
        },
        {"tool": "run_tests", "args": {}},
    ]n    it = iter(plan)

    def decide(_m):
        try:
            return next(it)
        except StopIteration:
            return {"tool": "done", "args": {"reason": "stop"}}

    rt = ToolRuntime(fixture_root=LEDGER, decide_fn=decide, max_steps=6, pytest_timeout=30)
    result = rt.run("fix ledger via anchor_edit")
    assert result.ok is True, result.error or result.reason
    assert result.score == 1.0
