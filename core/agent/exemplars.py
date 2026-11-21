"""Batch 7: kept-edit exemplars (ExpeL / Agent Workflow Memory style), flag ETHER_EXEMPLARS.

Every edit the honest gate KEPT (target test passes, 0 regressions, siblings pass) is stored as a
short before/after diff. A later goal may be shown ONE such diff from a different function as a
pattern hint. The store only ever holds gate-verified edits, so retrieval cannot teach a cheat the
gate did not already accept, and the reward is still the gate's 0/1 for the new goal.

Flag values (default "0" = off, no file written, prompts byte-identical):
  record  store kept edits only (warm the library during the Phase-0 baseline; prompts unchanged)
  1       store + offer the bandit arm "exemplar" (default prompt + one retrieved diff)

Anti-leak rules (a shown diff must never be this goal's answer):
  - never the same goal id, the same test node id, or the same (file, symbol)
  - never a diff that defines or assigns the goal's own short symbol name (would also trip the
    spoiler guard and burn the goal)
  - only rows whose own gate verdict was a keep
  - the arm is offered only once the library has a candidate, so cold-start pulls are not wasted
State: <root>/memory/learning/exemplars.json (private; memory/ is never published), written only
through core.spine.state_io.rmw (single-writer rule D3).
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.learning import ArmBehaviour

ARM = "exemplar"
MAX_ROWS = 500
BLOCK_CAP = 700
DIFF_CAP = 520
MIN_SCORE = 0.08
_TOK = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_STOP = frozenset({"self", "def", "return", "assert", "none", "true", "false", "test", "tests", "the", "and",
                   "for", "not", "import", "from", "with", "error", "file", "line", "pass"})


def mode() -> str:
    raw = (os.getenv("ETHER_EXEMPLARS") or "0").strip().lower()
    return raw if raw in ("0", "record", "1") else "0"


def recording() -> bool:
    return mode() in ("record", "1")


def arm_on() -> bool:
    return mode() == "1"


@dataclass(frozen=True)
class ExemplarBehaviour(ArmBehaviour):
    """The default arm plus one retrieved kept-edit diff."""

    use_exemplars: bool = True


def behaviour() -> ExemplarBehaviour:
    from core.learning import arm_behaviour

    base = arm_behaviour("default")
    return ExemplarBehaviour(prompt_addon=base.prompt_addon)


def path(root: Path) -> Path:
    return Path(root) / "memory" / "learning" / "exemplars.json"


# ---------------------------------------------------------------- store

def _func_text(text: str, symbol: str) -> str:
    try:
        tree = ast.parse(text or "")
    except SyntaxError:
        return ""
    body: Iterable[ast.stmt] = tree.body
    node = None
    for name in symbol.split("."):
        node = next((n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                     and n.name == name), None)
        if node is None:
            break
        body = getattr(node, "body", [])
    lines = (text or "").splitlines()
    if node is None:  # module-level assignment goal
        for n in tree.body:
            if isinstance(n, (ast.Assign, ast.AnnAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                if any(isinstance(t, ast.Name) and t.id == symbol for t in targets):
                    return "\n".join(lines[n.lineno - 1: n.end_lineno])
        return ""
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return "\n".join(lines[start - 1: node.end_lineno])


def diff_of(before: str, after: str, cap: int = DIFF_CAP) -> str:
    rows = list(difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=1))
    rows = [r for r in rows if not r.startswith(("---", "+++"))]
    out = "\n".join(rows)
    return out if len(out) <= cap else out[:cap].rsplit("\n", 1)[0] + "\n..."


def tokens(*parts: Any) -> List[str]:
    seen: Dict[str, None] = {}
    for p in parts:
        for t in _TOK.findall(str(p or "")):
            low = t.lower()
            if low not in _STOP:
                seen.setdefault(low, None)
            for sub in low.split("_"):
                if len(sub) >= 3 and sub not in _STOP:
                    seen.setdefault(sub, None)
    return list(seen)[:80]


def _goal_tokens(goal: Dict[str, Any]) -> List[str]:
    test_name = str(goal.get("nodeid") or "").split("::")[-1]
    return tokens(goal.get("error_kind"), str(goal.get("error") or "")[-400:], test_name,
                  goal.get("symbol"), goal.get("rule"))


def _valid(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("kept") is True and r.get("diff")]


def load(root: Path) -> List[Dict[str, Any]]:
    from core.spine.state_io import read_json

    p = path(root)
    return _valid(read_json(p, [])) if p.is_file() else []


def record_kept(root: Path, goal: Dict[str, Any], before_file: str, after_file: str,
                verdict: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Store one gate-kept edit. Called only on the keep branch of the honest gate."""
    if not recording():
        return None
    if verdict is not None and not verdict.get("ok"):
        return None  # belt and braces: only gate keeps enter the library
    symbol = str(goal.get("symbol") or "")
    before = _func_text(before_file, symbol)
    after = _func_text(after_file, symbol)
    if not after or before == after:
        return None
    diff = diff_of(before, after)
    if not diff.strip():
        return None
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "id": str(goal.get("id") or ""),
        "kind": goal.get("kind"),
        "file": goal.get("file"),
        "symbol": symbol,
        "nodeid": goal.get("nodeid"),
        "error_kind": goal.get("error_kind"),
        "error": str(goal.get("error") or "")[-200:],
        "span": bool(goal.get("span")),
        "tokens": _goal_tokens(goal),
        "diff": diff,
        "sha": hashlib.sha1(diff.encode("utf-8")).hexdigest()[:12],
        "kept": True,
        "uses": 0,
    }
    from core.spine.state_io import rmw

    rmw(path(root), lambda cur: ([r for r in _valid(cur) if r.get("id") != row["id"]] + [row])[-MAX_ROWS:], [])
    return row


# ---------------------------------------------------------------- retrieval

def leaks(goal: Dict[str, Any], row: Dict[str, Any]) -> bool:
    """True when showing `row` to `goal` could hand over this goal's own answer."""
    if row.get("id") and row.get("id") == goal.get("id"):
        return True
    if goal.get("nodeid") and row.get("nodeid") == goal.get("nodeid"):
        return True
    if row.get("file") == goal.get("file") and row.get("symbol") == goal.get("symbol"):
        return True
    name = str(goal.get("symbol") or "").split(".")[-1]
    if name:
        diff = str(row.get("diff") or "")
        if re.search(rf"def\s+{re.escape(name)}\s*\(", diff):
            return True
        if re.search(rf"^[+\- ]?\s*{re.escape(name)}\s*(?::[^=\n]+)?=(?!=)", diff, re.M):
            return True
    return False


def score(goal: Dict[str, Any], row: Dict[str, Any], df: Dict[str, int], n_docs: int) -> float:
    q = set(_goal_tokens(goal))
    d = set(row.get("tokens") or [])
    if not q or not d:
        return 0.0
    inter = q & d
    # idf-weighted overlap / union: rare shared words (an attribute name) beat common ones
    w = lambda t: math.log(1.0 + (n_docs + 1) / (1.0 + df.get(t, 0)))  # noqa: E731
    num = sum(w(t) for t in inter)
    den = sum(w(t) for t in (q | d)) or 1.0
    s = num / den
    if goal.get("error_kind") and goal.get("error_kind") == row.get("error_kind"):
        s += 0.1
    if goal.get("kind") == row.get("kind"):
        s += 0.02
    if bool(goal.get("span")) == bool(row.get("span")):
        s += 0.02
    return round(s, 4)


def retrieve(root: Path, goal: Optional[Dict[str, Any]], k: int = 1,
             rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    if not goal:
        return []
    rows = load(root) if rows is None else rows
    cands = [r for r in rows if not leaks(goal, r)]
    if not cands:
        return []
    df: Dict[str, int] = {}
    for r in rows:
        for t in set(r.get("tokens") or []):
            df[t] = df.get(t, 0) + 1
    scored = sorted(((score(goal, r, df, len(rows)), r) for r in cands), key=lambda x: (-x[0], str(x[1].get("ts"))))
    return [{**r, "score": s} for s, r in scored[:k] if s >= MIN_SCORE]


def available(root: Path, goal: Optional[Dict[str, Any]]) -> bool:
    """The arm is worth a pull only when there is a non-leaking candidate for this goal."""
    return arm_on() and bool(retrieve(root, goal, k=1))


def block(rows: List[Dict[str, Any]], room: int) -> str:
    """Prompt block. Never longer than min(BLOCK_CAP, room); room is what the caller can spare."""
    cap = min(BLOCK_CAP, max(0, room))
    if not rows or cap < 160:
        return ""
    r = rows[0]
    head = ("A different fix that passed this repo's tests before (a pattern hint, not your answer; "
            "edit only the function asked for):\n"
            f"Error ({r.get('error_kind')}): {str(r.get('error') or '')[-120:]}\n")
    body = str(r.get("diff") or "")
    room_left = cap - len(head) - 2
    if room_left < 80:
        return ""
    if len(body) > room_left:
        body = body[:room_left].rsplit("\n", 1)[0] + "\n..."
    return head + body + "\n"


def note_use(root: Path, exemplar_id: str) -> None:
    """Count a show that ended in a keep (for pruning later; the reuse rate lives in trajectories)."""
    from core.spine.state_io import rmw

    if not path(root).is_file():
        return

    def bump(cur: Any) -> List[Dict[str, Any]]:
        rows = _valid(cur)
        for r in rows:
            if r.get("id") == exemplar_id:
                r["uses"] = int(r.get("uses") or 0) + 1
        return rows

    rmw(path(root), bump, [])


def summary(root: Path, trajectories: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Library size + reuse: shown, kept-when-shown, and kept/attempt with vs without."""
    rows = load(root)
    out: Dict[str, Any] = {"mode": mode(), "library": len(rows)}
    if trajectories is None:
        try:
            from core.agent.outcome import trajectories as _t

            trajectories = _t(root)
        except Exception:
            trajectories = []
    graded = [t for t in trajectories if t.get("reward01") is not None]
    if any("exemplar_eligible" in t for t in trajectories):
        graded = [t for t in graded if t.get("exemplar_eligible")]  # like-for-like: both arms were possible
    shown = [t for t in graded if t.get("exemplar")]
    other = [t for t in graded if not t.get("exemplar")]
    out["shown"] = len(shown)
    out["kept_when_shown"] = sum(int(t.get("reward01") or 0) for t in shown)
    out["kept_per_attempt_shown"] = round(out["kept_when_shown"] / len(shown), 4) if shown else None
    out["kept_per_attempt_other"] = (round(sum(int(t.get("reward01") or 0) for t in other) / len(other), 4)
                                     if other else None)
    out["reuse_rate"] = round(len({t.get("exemplar") for t in shown}) / len(rows), 4) if rows else None
    return out
