"""Sub-function (span) goals for targets too large to rewrite in one reply (batch 6).

A function whose full text does not fit the reply cap used to be dropped ("too_large"). With
ETHER_SPAN_EDIT=1 (default on) such a goal gets a window of at most SPAN_LINES lines inside the
function, anchored on evidence: the deepest traceback frame inside it, else the line whose
string literals / names best match the failing assert. The model sees the window between
markers (plus a few read-only lines around it) and replies with replacement lines for the
window only. Apply checks the window text is unchanged since the scan (sha), re-indents,
compiles, keeps the function's name, and refuses protected paths. The gate is unchanged:
target test + siblings + guard suite, revert on any failure. Generate-only never counts.
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SPAN_LINES = 30
MIN_SPAN_LINES = 6
CONTEXT_LINES = 4
MARK_START = "# >>> EDIT START"
MARK_END = "# <<< EDIT END"
STOP = {"assert", "self", "None", "True", "False", "return", "import", "from", "test", "tests", "AssertionError",
        "where", "lower", "with", "text", "json", "dict", "list", "str", "len", "def", "for", "and", "not"}


def enabled() -> bool:
    return os.getenv("ETHER_SPAN_EDIT", "1") == "1"


def _func_node(tree: ast.Module, symbol: str):
    body, node = tree.body, None
    for name in symbol.split("."):
        node = next((n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                     and n.name == name), None)
        if node is None:
            return None
        body = getattr(node, "body", [])
    return node if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None


def _range(tree: ast.Module, goal: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """(first, last) line of the target: a function, or a module-level assignment (symbol_kind=assign)."""
    if goal.get("symbol_kind") == "assign":
        from core.agent.goal_source import _assign_span

        return _assign_span(tree, goal["symbol"])
    node = _func_node(tree, goal["symbol"])
    if node is None:
        return None
    return min([node.lineno] + [d.lineno for d in node.decorator_list]), node.end_lineno or node.lineno


def sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def evidence_words(text: str, test_src: str = "") -> List[str]:
    """Literals and identifiers from the failing assert lines (E lines + the assert in the test)."""
    lines = [ln for ln in (text or "").splitlines() if ln.lstrip().startswith(("E ", "assert ")) or "assert " in ln]
    lines += [ln for ln in (test_src or "").splitlines() if "assert " in ln]
    words: List[str] = []
    for ln in lines:
        for lit in re.findall(r"""["']([^"'\n]{3,60})["']""", ln):
            words.append(lit)
        for ident in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", ln):
            if ident not in STOP:
                words.append(ident)
    seen, out = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[:40]


def assert_words(root: Path, nodeid: str, text: str) -> List[str]:
    """Literals/identifiers of the test's own failing line (the deepest frame in the test file)."""
    rel = nodeid.split("::", 1)[0]
    hits = re.findall(rf"^{re.escape(rel)}:(\d+):", text or "", re.M)
    if not hits:
        return []
    try:
        line = (Path(root) / rel).read_text(encoding="utf-8").splitlines()[int(hits[-1]) - 1]
    except Exception:
        return []
    return evidence_words("", line)


def anchor_line(lines: List[str], start: int, end: int, words: List[str], min_score: float = 1.0) -> Optional[int]:
    """1-based line in [start, end] with the most evidence hits (literals weigh 2), or None."""
    best, best_score = None, 0.0
    for i in range(start, end + 1):
        ln = lines[i - 1]
        score = 0.0
        for w in words:
            if not w:
                continue
            if f'"{w}"' in ln or f"'{w}'" in ln:
                score += 2.0
            elif re.search(rf"\b{re.escape(w)}\b", ln):
                score += 1.0
        if score > best_score:
            best, best_score = i, score
    return best if best_score >= min_score else None


def window(start: int, end: int, anchor: int, n: int = SPAN_LINES) -> Tuple[int, int]:
    """n-line window inside the function body around the anchor (never the def line)."""
    body_start = start + 1
    lo = max(body_start, anchor - n // 3)
    hi = min(end, lo + n - 1)
    lo = max(body_start, min(lo, hi - n + 1))
    return lo, hi


def make_span(root: Path, goal: Dict[str, Any], text: str, test_src: str = "",
              frame_line: Optional[int] = None, words: Optional[List[str]] = None,
              min_score: float = 1.0, cap_tokens: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """The goal with a "span" added, or None when there is no evidence anchor in the function."""
    from core.agent.goal_quality import protected

    if not enabled() or protected(goal.get("file", "")):
        return None
    path = Path(root) / goal["file"]
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception:
        return None
    rng = _range(tree, goal)
    if rng is None:
        return None
    start, end = rng
    lines = src.splitlines()
    anchor = frame_line if frame_line and start < frame_line <= end else None
    via = "frame"
    if anchor is None:
        anchor = anchor_line(lines, start + 1, end, words if words is not None else evidence_words(text, test_src),
                             min_score=min_score)
        via = "assert_literal" if words is not None else "evidence"
    if anchor is None:
        return None
    n = SPAN_LINES
    while True:
        lo, hi = window(start, end, anchor, n)
        block = "\n".join(lines[lo - 1: hi])
        if cap_tokens is None or int((len(block) / 3.3 + 1) * 1.1) <= cap_tokens or n <= MIN_SPAN_LINES:
            break
        n = max(MIN_SPAN_LINES, n * 2 // 3)
    return {**goal, "span": {"start": lo, "end": hi, "anchor": anchor, "anchor_via": via, "sha": sha(block),
                             "func_start": start, "func_end": end}}


def span_text(root: Path, goal: Dict[str, Any]) -> str:
    sp = goal["span"]
    try:
        lines = (Path(root) / goal["file"]).read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    return "\n".join(lines[sp["start"] - 1: sp["end"]])


def fits(root: Path, goal: Dict[str, Any], reply_max: int, est_tokens) -> bool:
    cur = span_text(root, goal)
    return bool(cur) and int(est_tokens(cur) * 1.1) <= reply_max


def context_block(root: Path, goal: Dict[str, Any], bare: bool = False) -> str:
    """def line, read-only lines around the window, and the window between markers.

    bare=True (the no_context arm): only the marked window. The window is the edit target, not
    workspace context, so an ablation arm must never hide it (else no reply can be applied).
    """
    sp = goal["span"]
    lines = (Path(root) / goal["file"]).read_text(encoding="utf-8").splitlines()
    if bare:
        return "\n".join([MARK_START + f" (lines {sp['start']}-{sp['end']})"] +
                         lines[sp["start"] - 1: sp["end"]] + [MARK_END])
    head = lines[sp["func_start"] - 1]
    before = lines[max(sp["func_start"], sp["start"] - 1 - CONTEXT_LINES): sp["start"] - 1]
    after = lines[sp["end"]: min(sp["func_end"], sp["end"] + CONTEXT_LINES)]
    out = [head, "    ..."] + before + [MARK_START + f" (lines {sp['start']}-{sp['end']})"] + \
        lines[sp["start"] - 1: sp["end"]] + [MARK_END] + after + ["    ..."]
    return "\n".join(out)


def prompt_tail(goal: Dict[str, Any]) -> str:
    sp = goal["span"]
    return (f"Reply with ONLY the replacement for lines {sp['start']}-{sp['end']} of `{goal['symbol']}` "
            f"(the lines between `{MARK_START}` and `{MARK_END}`), same indentation, no markdown. "
            "Everything outside the markers stays as it is.\n")


def extract(reply: str) -> str:
    text = re.sub(r"```(?:python)?", "", (reply or "").replace("\r\n", "\n"))
    if MARK_START in text:
        text = text.split(MARK_START, 1)[1]
        text = text.split("\n", 1)[1] if "\n" in text else ""
    if MARK_END in text:
        text = text.split(MARK_END, 1)[0]
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _indent(s: str) -> int:
    return len(s) - len(s.lstrip())


def apply(root: Path, goal: Dict[str, Any], block: str) -> Dict[str, Any]:
    """Replace the window. Returns {"ok", "original"} like goal_source.apply_edit."""
    from core.agent.goal_quality import protected

    if protected(goal.get("file", "")):
        return {"ok": False, "reason": "protected path"}
    if not block.strip():
        return {"ok": False, "reason": "empty edit"}
    sp = goal["span"]
    path = Path(root) / goal["file"]
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    old = lines[sp["start"] - 1: sp["end"]]
    if sha("\n".join(old)) != sp.get("sha"):
        return {"ok": False, "reason": "stale span"}
    new_lines = block.split("\n")
    old_ind = min((_indent(x) for x in old if x.strip()), default=0)
    new_ind = min((_indent(x) for x in new_lines if x.strip()), default=0)
    if new_ind != old_ind:
        shift = old_ind - new_ind
        new_lines = [(" " * shift + x if shift > 0 else x[min(-shift, _indent(x)):]) if x.strip() else x
                     for x in new_lines]
    if len(new_lines) > 2 * SPAN_LINES:
        return {"ok": False, "reason": "reply longer than twice the window"}
    if new_lines == old:
        return {"ok": False, "reason": "no change"}
    new = "\n".join(lines[: sp["start"] - 1] + new_lines + lines[sp["end"]:]) + "\n"
    try:
        tree = ast.parse(new)
        compile(new, str(path), "exec")
    except SyntaxError as exc:
        return {"ok": False, "reason": f"syntax: {exc.msg}"}
    if _range(tree, goal) is None:
        return {"ok": False, "reason": "edit removed the target"}
    path.write_text(new, encoding="utf-8")
    return {"ok": True, "original": original, "span": True}
