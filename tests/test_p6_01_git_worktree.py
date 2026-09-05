"""p6_01 FAST: read-only git tools + one sibling worktree."""
from __future__ import annotations

import subprocess
from pathlib import Path

from core.loop.git_tools import git_branch, git_log
from core.loop.worktree import add_worktree, remove_worktree


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, timeout=20)


def test_git_log_and_branch_on_tmp_repo(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    monkeypatch.chdir(repo)
    log = git_log(3)
    assert log["ok"] is True
    assert "init" in log["stdout"]
    br = git_branch()
    assert br["ok"] is True
    assert br["branch"]


def test_add_and_remove_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    wt = tmp_path / "wt"
    added = add_worktree(wt, repo=repo, detach=True)
    assert added["ok"] is True
    assert wt.exists()
    removed = remove_worktree(wt, repo=repo)
    assert removed["ok"] is True
