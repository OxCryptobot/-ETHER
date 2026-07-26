"""Git self-heal helpers for flywheel pull."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict

ROOT = Path(__file__).resolve().parents[1]


def safe_pull(git_fn: Callable[..., Dict[str, Any]]) -> Dict[str, Any]:
    """Attempt ff-only pull; recover from MERGE_HEAD when allowed."""
    merge_head = ROOT / ".git" / "MERGE_HEAD"
    if merge_head.exists():
        if os.getenv("ETHER_GIT_RESET_OK", "0") == "1":
            git_fn("merge", "--abort")
            r = git_fn("reset", "--hard", "origin/main")
            r["healed"] = "reset_hard_after_merge"
            return r
        return {
            "ok": False,
            "returncode": 1,
            "stdout": "",
            "stderr": "MERGE_HEAD exists; set ETHER_GIT_RESET_OK=1 to auto-reset",
            "duration_s": 0.0,
            "healed": False,
        }

    pull = git_fn("pull", "--ff-only", "origin", "main")
    if pull.get("ok"):
        return pull

    err = (pull.get("stderr") or "") + (pull.get("stdout") or "")
    if "unrelated histories" in err or "divergent" in err.lower() or "MERGE_HEAD" in err:
        if os.getenv("ETHER_GIT_RESET_OK", "0") == "1":
            git_fn("merge", "--abort")
            git_fn("fetch", "origin")
            r = git_fn("reset", "--hard", "origin/main")
            r["healed"] = "reset_hard_divergent"
            return r
    return pull
