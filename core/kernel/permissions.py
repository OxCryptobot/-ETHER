"""Tool permissions. Read default. Write after a test plan. Shell off."""
from __future__ import annotations

READ = frozenset({"list_files", "read_file", "grep", "glob", "git_diff", "git_status", "git_log", "git_branch"})
WRITE = frozenset({"write_file", "apply_patch", "rollback", "rename", "delete", "edit_lines"})
VERIFY = frozenset({"run_tests", "pep8_review", "done", "bug_comments"})
SHELL = frozenset({"shell", "bash"})

def allow(tool: str, *, writes_enabled: bool = True, shell_enabled: bool = False) -> bool:
    name = (tool or "").strip()
    if name in READ or name in VERIFY:
        return True
    if name in WRITE:
        return bool(writes_enabled)
    if name in SHELL:
        return bool(shell_enabled)
    return False
