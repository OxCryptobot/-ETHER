"""Teacher takeover when LIVE observe-loops.

Playbook PASS is teacher_playbook, never model_skill.
Comment-derived replace_once is craft_helper — still not unaided 4B skill.
Living-agent waits for policy=model on merge+ledger LIVE ×3.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

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

TAKEOVER_AFTER = 2

_BUG_SHOULD_INLINE = re.compile(
    r"^(?P<indent>\s*)(?P<stmt>.+?)\s*#\s*BUG:\s*should\s+(?!also\b)(?P<fix>.+?)\s*$",
    re.IGNORECASE,
)
_BUG_SHOULD_LINE = re.compile(
    r"^(?P<indent>\s*)#\s*BUG:\s*should(?P<also>\s+also)?\s+(?P<fix>.+?)\s*$",
    re.IGNORECASE,
)

# Fixture books are remainder fallbacks only. Prefer mutations_from_bug_comments.
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


def _clean_fix(raw: str) -> str:
    return (raw or "").strip().rstrip(".")


def mutations_from_bug_comments(path: str, source: str) -> List[Dict[str, Any]]:
    """Turn author-marked BUG comments into unique replace_once steps.

    Grammars (no fixture dictionary):
    - ``stmt  # BUG: should <fix>`` → replace the statement with <fix>
    - ``# BUG: should <fix>`` on the previous line → insert <fix> before next code
    - ``# BUG: should also <fix>`` → insert <fix> immediately before the next return

    Missing-block bugs with no parseable ``should`` stay on the teacher book
    until 4B emits them unaided (policy=model).
    """
    steps: List[Dict[str, Any]] = []
    lines = (source or "").splitlines()
    n = len(lines)
    i = 0
    while i < n:
        raw = lines[i]
        inline = _BUG_SHOULD_INLINE.match(raw)
        if inline:
            indent = inline.group("indent")
            fix = _clean_fix(inline.group("fix"))
            steps.append(
                {
                    "tool": "replace_once",
                    "args": {"path": path, "old": raw, "new": indent + fix},
                    "source": "bug_comment",
                }
            )
            i += 1
            continue
        lined = _BUG_SHOULD_LINE.match(raw)
        if lined:
            indent = lined.group("indent")
            fix = _clean_fix(lined.group("fix"))
            also = bool(lined.group("also"))
            j = i + 1
            while j < n and (
                not lines[j].strip() or lines[j].lstrip().startswith("#")
            ):
                j += 1
            if j >= n:
                i += 1
                continue
            if also:
                k = j
                while k < n and not re.match(r"^\s*return\b", lines[k]):
                    k += 1
                if k < n:
                    ret = lines[k]
                    ret_indent_m = re.match(r"^(\s*)", ret)
                    ret_indent = ret_indent_m.group(1) if ret_indent_m else indent
                    old = "\n".join(lines[j : k + 1])
                    inserted = list(lines[j:k]) + [ret_indent + fix, ret]
                    new = "\n".join(inserted)
                    if old != new:
                        steps.append(
                            {
                                "tool": "replace_once",
                                "args": {"path": path, "old": old, "new": new},
                                "source": "bug_comment",
                            }
                        )
            else:
                nxt = lines[j]
                nxt_indent_m = re.match(r"^(\s*)", nxt)
                nxt_indent = nxt_indent_m.group(1) if nxt_indent_m else indent
                new = nxt_indent + fix + "\n" + nxt
                steps.append(
                    {
                        "tool": "replace_once",
                        "args": {"path": path, "old": nxt, "new": new},
                        "source": "bug_comment",
                    }
                )
            i += 1
            continue
        i += 1
    return steps


def mutations_from_workspace(root: Any, *, limit: int = 24) -> List[Dict[str, Any]]:
    """Derive suggested replace_once steps from every non-test .py under root."""
    from pathlib import Path

    steps: List[Dict[str, Any]] = []
    if root is None:
        return steps
    base = Path(root)
    if not base.exists():
        return steps
    for fp in sorted(base.rglob("*.py")):
        if "__pycache__" in fp.parts or "tests" in fp.parts:
            continue
        try:
            rel = str(fp.relative_to(base)).replace("\\", "/")
        except ValueError:
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        steps.extend(mutations_from_bug_comments(rel, text))
        if len(steps) >= limit:
            return steps[:limit]
    return steps[:limit]


def _extract_json_objects(raw: str) -> List[str]:
    out: List[str] = []
    i = 0
    text = raw or ""
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        while j < len(text):
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        out.append(text[i : j + 1])
                        break
            j += 1
        i = j + 1 if depth == 0 else i + 1
    return out


def suggested_from_messages(messages: Optional[List[Dict[str, str]]]) -> List[Dict[str, Any]]:
    """Read suggested[] off the latest tool observation in the transcript."""
    for m in reversed(messages or []):
        if (m.get("role") or "") != "user":
            continue
        content = m.get("content") or ""
        for blob in _extract_json_objects(content):
            try:
                obj = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("suggested"):
                sug = obj.get("suggested")
                if isinstance(sug, list):
                    return [s for s in sug if isinstance(s, dict) and s.get("tool")]
    return []


def _old_key(step: Dict[str, Any]) -> str:
    args = step.get("args") if isinstance(step.get("args"), dict) else {}
    return str(args.get("old") or args.get("contains") or "")


def wrap_live_decide(fixture: str, inner: Callable) -> Callable:
    book = list(PLAYBOOKS.get(fixture) or [])
    state: Dict[str, Any] = {
        "observe": 0,
        "i": 0,
        "craft_i": 0,
        "takeover": False,
        "policy": "model",
        "inner_calls": 0,
        "tested": False,
        "applied_old": set(),
    }

    def _next_teacher_or_craft(messages) -> Dict[str, Any]:
        sug = suggested_from_messages(messages)
        while state["craft_i"] < len(sug):
            step = sug[state["craft_i"]]
            state["craft_i"] += 1
            key = _old_key(step)
            if key and key in state["applied_old"]:
                continue
            if key:
                state["applied_old"].add(key)
            state["policy"] = "craft_helper"
            return step
        while state["i"] < len(book):
            step = book[state["i"]]
            state["i"] += 1
            tool = str(step.get("tool") or "")
            if tool in ("bug_comments", "run_tests", "done"):
                continue
            key = _old_key(step)
            if key and key in state["applied_old"]:
                continue
            # Skip book replace_once whose `new` already matches a craft `new`.
            args = step.get("args") if isinstance(step.get("args"), dict) else {}
            new = str(args.get("new") or "")
            already_new = False
            for prev in sug[: state["craft_i"]]:
                pargs = prev.get("args") if isinstance(prev.get("args"), dict) else {}
                if new and str(pargs.get("new") or "") == new:
                    already_new = True
                    break
            if already_new:
                continue
            if key:
                state["applied_old"].add(key)
            state["policy"] = "teacher_playbook"
            return step
        if not state["tested"]:
            state["tested"] = True
            return {"tool": "run_tests", "args": {}}
        return {"tool": "done", "args": {"reason": str(state["policy"])}}

    def decide(messages):
        # I-005: never call the LLM after takeover. Playbook/craft owns the turn.
        if state["takeover"] and (book or suggested_from_messages(messages)):
            return _next_teacher_or_craft(messages)
        if state["takeover"]:
            return _next_teacher_or_craft(messages)

        state["inner_calls"] += 1
        decision = inner(messages)
        if not isinstance(decision, dict):
            return decision
        tool = str(decision.get("tool") or "")
        if tool in MUTATE:
            state["observe"] = 0
            return decision
        if tool in OBSERVE:
            state["observe"] += 1
        if book and state["observe"] >= TAKEOVER_AFTER:
            state["takeover"] = True
            # Prefer comment-derived steps once the observation exists; otherwise
            # start the teacher book (usually bug_comments to populate suggested).
            sug = suggested_from_messages(messages)
            if sug:
                state["policy"] = "craft_helper"
                return _next_teacher_or_craft(messages)
            state["policy"] = "teacher_playbook"
            if state["i"] < len(book):
                step = book[state["i"]]
                state["i"] += 1
                return step
            return _next_teacher_or_craft(messages)
        return decision

    decide.policy = lambda: state["policy"]  # type: ignore[attr-defined]
    decide.takeover = lambda: bool(state["takeover"])  # type: ignore[attr-defined]
    decide.inner_calls = lambda: int(state["inner_calls"])  # type: ignore[attr-defined]
    return decide
