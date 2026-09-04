"""Hard observe-loop breaker used by hard_live_boot.

Hints were ignored on p1_248 (6× read_file → timeout). After MAX_OBSERVE_STREAK
read/list calls, the next observe tool is rewritten. After MAX_OBSERVE_STREAK+2
the loop is terminated. That is a tool-order fix, not a budget bump.

p3_46: kill used to force `done` even when the 4B chose replace_once, and even
after a mutate that had not been run_tests'd. Kill never overrides mutate or
run_tests. After a mutate, kill routes to run_tests.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

MAX_OBSERVE_STREAK = 3
KILL_STREAK = 5

MUTATE = frozenset(
    {
        "write_file",
        "apply_patch",
        "edit_lines",
        "replace_once",
        "anchor_edit",
        "rollback",
    }
)
PROTECTED = MUTATE | frozenset({"run_tests", "done", "pep8_review"})
OBSERVE = frozenset(
    {
        "read_file",
        "list_files",
        "grep",
        "glob",
        "ast_outline",
        "bug_comments",
        "_retry",
    }
)


def rewrite(
    tool: str,
    streak: int,
    *,
    mutated: bool = False,
) -> Optional[Dict[str, Any]]:
    name = (tool or "").strip()
    if name in PROTECTED:
        return None
    if streak >= KILL_STREAK:
        if mutated:
            return {
                "tool": "run_tests",
                "args": {"reason": f"observe_loop_kill streak={streak} last={name}"},
            }
        return {
            "tool": "done",
            "args": {"reason": f"observe_loop_kill streak={streak} last={name}"},
        }
    if streak >= MAX_OBSERVE_STREAK and name in OBSERVE:
        return {"tool": "bug_comments", "args": {}}
    return None
