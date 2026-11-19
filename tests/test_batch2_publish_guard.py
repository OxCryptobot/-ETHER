"""Batch 2: the worktree publish must not revert upstream code (clobber guard)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.origin_publish import code_paths_upstream_changed


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def _runner(cwd: Path):
    def run(argv):
        return subprocess.run(argv[:1] + ["-C", str(cwd)] + argv[1:], capture_output=True, text=True)
    return run


def test_upstream_change_is_never_copied_over(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    a = tmp_path / "a"
    subprocess.run(["git", "clone", "-q", str(origin), str(a)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        _git(a, "config", k, v)
    (a / "core").mkdir()
    (a / "core" / "plan.py").write_text("def heartbeat_plan():\n    return 1\n")
    (a / "core" / "mine.py").write_text("X = 1\n")
    (a / "artifacts").mkdir()
    (a / "artifacts" / "x.json").write_text("{}\n")
    _git(a, "add", "-A"); _git(a, "commit", "-qm", "base"); _git(a, "push", "-q", "origin", "HEAD:main")
    b = tmp_path / "b"
    subprocess.run(["git", "clone", "-q", str(origin), str(b)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        _git(b, "config", k, v)
    (b / "core" / "plan.py").write_text("def heartbeat_plan():\n    return 2  # upstream fix\n")
    _git(b, "commit", "-qam", "fix"); _git(b, "push", "-q", "origin", "HEAD:main")
    (a / "core" / "mine.py").write_text("X = 2\n")
    _git(a, "commit", "-qam", "local"); _git(a, "fetch", "-q", "origin")
    skipped = code_paths_upstream_changed("git", _runner(a), ["core/plan.py", "core/mine.py", "artifacts/x.json"])
    assert skipped == ["core/plan.py"]
