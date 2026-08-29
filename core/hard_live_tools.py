"""Hard-LIVE tool helpers — numbered reads, line edits, bug-comment scan.

4B live merge/ledger fails as an observe-loop: 10x read_file, zero writes,
max_steps. Small models cannot emit a full write_file in 512 tokens and
cannot copy exact apply_patch strings. These helpers give them tools
they can actually call.

Does not leak fixture solutions. Does not lift wheels.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

OBSERVE_TOOLS = frozenset(
    {"list_files", "read_file", "grep", "glob", "bug_comments", "_retry"}
)
MUTATE_TOOLS = frozenset(
    {"write_file", "apply_patch", "edit_lines", "rollback"}
)
BUG_RX = re.compile(r"\b(BUG|FIXME|XXX)\b", re.IGNORECASE)

MAX_OBSERVE_STREAK = 3


def number_lines(text: str, *, start: int = 1, end: Optional[int] = None) -> str:
    """Render 1-indexed `NNNN|line` so edit_lines can target spans."""
    lines = (text or "").splitlines()
    lo = max(1, int(start))
    hi = len(lines) if end is None else min(len(lines), int(end))
    if hi < lo:
        return ""
    out = []
    for i in range(lo, hi + 1):
        out.append(f"{i:4d}|{lines[i - 1]}")
    return "\n".join(out)


def edit_lines(body: str, start_line: int, end_line: int, new: str) -> str:
    """Replace inclusive 1-indexed span with `new`. Fail-closed on bad range."""
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


def extract_bug_comments(workspace: Path, *, limit: int = 40) -> List[Dict[str, Any]]:
    """Scan non-test .py files for author-marked BUG/FIXME/XXX comments."""
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
        "Next tool MUST be edit_lines, apply_patch, or write_file. "
        "Re-reading the same file is a FAIL. Use numbered lines from "
        "read_file with edit_lines start_line/end_line/new."
    )


def should_break_observe(streak: int) -> bool:
    return int(streak) >= MAX_OBSERVE_STREAK
