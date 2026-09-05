"""Read-only git tools for the loop. Wraps chat_git_tools. No shell=True."""
from __future__ import annotations

import subprocess
from typing import Any, Dict

from core.chat_git_tools import git_diff, git_status

__all__ = ["git_status", "git_diff", "git_log", "git_branch"]


def git_log(n: int = 5) -> Dict[str, Any]:
    count = max(1, min(int(n), 20))
    result = subprocess.run(
        ["git", "log", f"-{count}", "--oneline"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return {
        "ok": result.returncode == 0,
        "tool": "git_log",
        "stdout": (result.stdout or "")[:2000],
        "stderr": (result.stderr or "")[:400],
    }


def git_branch() -> Dict[str, Any]:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return {
        "ok": result.returncode == 0,
        "tool": "git_branch",
        "branch": (result.stdout or "").strip(),
        "stderr": (result.stderr or "")[:400],
    }
