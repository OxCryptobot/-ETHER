"""Hard-LIVE helpers — numbered reads, line edits, flex patch, AST outline.

Does not leak fixture solutions. Does not lift wheels.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

OBSERVE_TOOLS = frozenset(
    {
        "list_files",
        "read_file",
        "grep",
        "glob",
        "bug_comments",
        "ast_outline",
        "_retry",
    }
)
MUTATE_TOOLS = frozenset(
    {"write_file", "apply_patch", "edit_lines", "replace_once", "rollback"}
)
BUG_RX = re.compile(r"\b(BUG|FIXME|XXX)\b", re.IGNORECASE)
MAX_OBSERVE_STREAK = 3


def number_lines(text: str, *, start: int = 1, end: Optional[int] = None) -> str:
    lines = (text or "").splitlines()
    lo = max(1, int(start))
    hi = len(lines) if end is None else min(len(lines), int(end))
    if hi < lo:
        return ""
    return "\n".join(f"{i:4d}|{lines[i - 1]}" for i in range(lo, hi + 1))


def edit_lines(body: str, start_line: int, end_line: int, new: str) -> str:
    lines = (body or "").splitlines(keepends=True)
    n = len(lines)
    s = int(start_line)
    e = int(end_line)
    if s < 1 or e < s or e > n:
        raise ValueError(f"bad span {s}-{e} for {n} lines")
    prefix = "".join(lines[: s - 1])
    suffix = "".join(lines[e:])
    chunk = new if new is not None else ""
    if chunk and not chunk.endswith("\n") and suffix:
        chunk = chunk + "\n"
    return prefix + chunk + suffix


def flex_replace(body: str, old: str, new: str) -> Tuple[str, str]:
    """Exact unique replace, then unique-line fallback. Fail-closed."""
    if not old:
        raise ValueError("old must be non-empty")
    n = body.count(old)
    if n == 1:
        return body.replace(old, new, 1), "exact"
    if n > 1:
        raise ValueError(f"old matched {n} times; must be unique")
    old_s = old.strip()
    hits = [i for i, line in enumerate(body.splitlines()) if line.strip() == old_s]
    if len(hits) == 1:
        lines = body.splitlines(keepends=True)
        idx = hits[0]
        indent_m = re.match(r"^[ \t]*", lines[idx])
        prefix = indent_m.group(0) if indent_m else ""
        if "\n" not in new:
            repl = prefix + new.lstrip()
            if lines[idx].endswith("\n"):
                repl += "\n"
        else:
            repl = new if new.endswith("\n") or not lines[idx].endswith("\n") else new + "\n"
        lines[idx] = repl
        return "".join(lines), "stripped-line"
    raise ValueError("old not found (exact and stripped-line miss)")


def ast_outline(text: str) -> List[Dict[str, Any]]:
    try:
        tree = ast.parse(text or "")
    except SyntaxError as e:
        return [{"error": f"AST: {e.msg}", "line": e.lineno}]
    out: List[Dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(
                {
                    "kind": type(node).__name__,
                    "name": node.name,
                    "line": int(node.lineno),
                }
            )
    return out


def extract_bug_comments(workspace: Path, *, limit: int = 40) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    if workspace is None or not Path(workspace).exists():
        return hits
    root = Path(workspace)
    for fp in sorted(root.rglob("*.py")):
        if "__pycache__" in fp.parts or "tests" in fp.parts:
            continue
        try:
            rel = str(fp.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if BUG_RX.search(line):
                hits.append({"path": rel, "line": i, "text": line.strip()[:200]})
                if len(hits) >= limit:
                    return hits
    return hits


def observe_loop_hint(streak: int, last_paths: Optional[List[str]] = None) -> str:
    paths = ", ".join(last_paths or []) or "(already listed)"
    return (
        f"STOP observing (streak={streak}). Files already seen: {paths}. "
        "Next tool MUST be edit_lines, replace_once, apply_patch, or write_file."
    )


def should_break_observe(streak: int) -> bool:
    return int(streak) >= MAX_OBSERVE_STREAK
