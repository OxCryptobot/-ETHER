"""Hard observe-loop breaker used by hard_live_boot.

Hints were ignored on p1_248 (6× read_file → timeout). After MAX_OBSERVE_STREAK
read/list calls, the next observe tool is rewritten. After MAX_OBSERVE_STREAK+2
the loop is terminated. That is a tool-order fix, not a budget bump.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

MAX_OBSERVE_STREAK = 3
KILL_STREAK = 5


def rewrite(tool: str, streak: int) -> Optional[Dict[str, Any]]:
    name = (tool or "").strip()
    if streak >= KILL_STREAK:
        return {
            "tool": "done",
            "args": {"reason": f"observe_loop_kill streak={streak} last={name}"},
        }
    if streak >= MAX_OBSERVE_STREAK and name in {
        "read_file",
        "list_files",
        "grep",
        "glob",
        "ast_outline",
        "_retry",
    }:
        return {"tool": "bug_comments", "args": {}}
    return None
