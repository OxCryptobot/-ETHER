"""Teacher takeover when LIVE observe-loops.

Playbook PASS is teacher_playbook, never model_skill. Generalize BUG comments
into replace_once when we can; remainder/missing-block still uses the fixture
book under wheels.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List

OBSERVE = {
    "list_files",
    "read_file",
    "grep",
    "glob",
    "bug_comments",
    "ast_outline",
    "_retry",
}
MUTATE = {
    "write_file",
    "apply_patch",
    "edit_lines",
    "replace_once",
    "anchor_edit",
    "rollback",
}

_BUG_SHOULD = re.compile(
    r"^(?P<indent>\s*)(?P<stmt>.+?)\s*#\s*BUG:\s*should\s+(?P<fix>.+?)\s*$",
    re.IGNORECASE,
)

PLAYBOOKS: Dict[str, List[Dict[str, Any]]] = {
    "merge": [
        {"tool": "bug_comments", "args": {"path": "merge.py"}},
        {
            "tool": "replace_once",
            "args": {
                "path": "merge.py",
                "old": "return b  # BUG: should return list(b)",
                "new": "return list(b)",
            },
        },
        {
            "tool": "replace_once",
            "args": {
                "path": "merge.py",
                "old": "return a  # BUG: should return list(a)",
                "new": "return list(a)",
            },
        },
        {
            "tool": "replace_once",
            "args": {
                "path": "merge.py",
                "old": "    if i < len(a):\n        out.extend(a[i:])\n    return out",
                "new": (
                    "    if i < len(a):\n"
                    "        out.extend(a[i:])\n"
                    "    if j < len(b):\n"
                    "        out.extend(b[j:])\n"
                    "    return out"
                ),
            },
        },
        {"tool": "run_tests", "args": {}},
        {"tool": "done", "args": {"reason": "playbook_merge"}},
    ],
    "ledger": [
        {"tool": "bug_comments", "args": {"path": "ledger.py"}},
        {
            "tool": "anchor_edit",
            "args": {
                "path": "ledger.py",
                "contains": "b.credit(amount)",
                "new": "        a.debit(amount)\n        b.credit(amount)",
            },
        },
        {
            "tool": "replace_once",
            "args": {
                "path": "ledger.py",
                "old": "return s + s",
                "new": "return s",
            },
        },
        {"tool": "run_tests", "args": {}},
        {"tool": "done", "args": {"reason": "playbook_ledger"}},
    ],
}


def mutations_from_bug_comments(path: str, source: str) -> List[Dict[str, Any]]:
    """Turn `# BUG: should <stmt>` lines into unique replace_once steps.

    Missing-block bugs (no comment on the forgotten code) cannot be derived
    this way — those stay on the teacher book until 4B emits them unaided.
    """
    steps: List[Dict[str, Any]] = []
    for raw in (source or "").splitlines():
        m = _BUG_SHOULD.match(raw)
        if not m:
            continue
        indent = m.group("indent")
        fix = m.group("fix").strip().rstrip(".")
        new = indent + fix
        steps.append(
            {
                "tool": "replace_once",
                "args": {"path": path, "old": raw, "new": new},
                "source": "bug_comment",
            }
        )
    return steps


def wrap_live_decide(fixture: str, inner: Callable) -> Callable:
    book = list(PLAYBOOKS.get(fixture) or [])
    state = {"observe": 0, "i": 0, "takeover": False, "policy": "model"}

    def decide(messages):
        if state["takeover"] and book:
            if state["i"] >= len(book):
                return {"tool": "done", "args": {"reason": "playbook_exhausted"}}
            step = book[state["i"]]
            state["i"] += 1
            return step
        decision = inner(messages)
        if not isinstance(decision, dict):
            return decision
        tool = str(decision.get("tool") or "")
        if tool in MUTATE:
            state["observe"] = 0
            return decision
        if tool in OBSERVE:
            state["observe"] += 1
        if book and state["observe"] >= 2:
            state["takeover"] = True
            state["policy"] = "teacher_playbook"
            step = book[state["i"]]
            state["i"] += 1
            return step
        return decision

    decide.policy = lambda: state["policy"]  # type: ignore[attr-defined]
    decide.takeover = lambda: bool(state["takeover"])  # type: ignore[attr-defined]
    return decide
