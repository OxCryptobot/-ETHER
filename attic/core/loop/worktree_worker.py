"""Run pytest in one sibling worktree. Same 4B. No second personality."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.loop.worktree import add_worktree, remove_worktree


def pytest_in_worktree(workspace: Path, *, repo: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(workspace)
    dest = root.parent / f"{root.name}_wt"
    added = add_worktree(dest, repo=repo or root, detach=True)
    if not added.get("ok"):
        return {
            "ok": False,
            "via": "worktree",
            "error": added.get("stderr") or added.get("error") or "worktree_add_failed",
        }
    try:
        from core.loop.living import run_tests

        result = run_tests(workspace=dest)
        result["via"] = "worktree"
        result["worktree"] = str(dest)
        return result
    finally:
        remove_worktree(dest, repo=repo or root)
