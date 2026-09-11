"""Phase 6 FAST: AST intel + native schema + worktree list. Not Claude Code."""
from __future__ import annotations

from pathlib import Path

from core.loop.ast_intel import goto_def, hover
from core.loop.native_tools import ollama_tools, schema_ok
from core.loop.worktree import add_worktree, remove_worktree
from core.loop.git_tools import git_branch, git_log


def test_ast_hover_on_this_file() -> None:
    here = Path(__file__)
    out = hover(str(here), "test_ast_hover_on_this_file")
    assert out["via"] == "ast_lite"
    assert out["ok"] is True
    gd = goto_def(str(here), "test_ast_hover_on_this_file")
    assert gd["ok"] is True


def test_native_schema_has_git_and_tests() -> None:
    assert schema_ok() is True
    names = [t["function"]["name"] for t in ollama_tools()]
    assert "git_status" in names
    assert "run_tests" in names


def test_git_log_and_branch() -> None:
    b = git_branch()
    assert "branch" in b
    lg = git_log(3)
    assert "stdout" in lg


def test_worktree_api_exists() -> None:
    assert callable(add_worktree)
    assert callable(remove_worktree)
