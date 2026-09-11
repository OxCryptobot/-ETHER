"""One sibling git worktree. Not a mesh. Fail-closed if git refuses."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


def add_worktree(path: Path, *, repo: Optional[Path] = None, detach: bool = True) -> Dict[str, Any]:
    dest = Path(path)
    cmd = ["git", "worktree", "add"]
    if detach:
        cmd.append("--detach")
    cmd.append(str(dest))
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo) if repo is not None else None,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "path": str(dest)}
    return {
        "ok": result.returncode == 0,
        "path": str(dest),
        "stdout": (result.stdout or "")[:400],
        "stderr": (result.stderr or "")[:400],
    }


def remove_worktree(path: Path, *, repo: Optional[Path] = None) -> Dict[str, Any]:
    dest = Path(path)
    try:
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(dest)],
            cwd=str(repo) if repo is not None else None,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "path": str(dest)}
    return {"ok": result.returncode == 0, "path": str(dest)}


def list_worktrees(*, repo: Optional[Path] = None) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(repo) if repo is not None else None,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "worktrees": []}
    rows = [ln[5:] for ln in (result.stdout or "").splitlines() if ln.startswith("worktree ")]
    return {"ok": result.returncode == 0, "worktrees": rows, "n": len(rows)}
