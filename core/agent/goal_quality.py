"""Goal-quality guard. A goal must be able to prove a capability.

Rejected (batch 2, 2026-11-19):
- constant: every assert in the goal test is `f() == <literal>` with no args
  (describe() == 'attach', add_name() == 'add', failing_test() == 'found').
  Passing it proves the model can copy a string, nothing else.
- spoiler: the prompt contains the answer (a full `def <symbol>` body).
- self_edit: the target is a test file, the writer's own loop, or the Matrix.
"""
from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List

PROTECTED_PREFIXES = (
    "tests/", "core/agent/", "scripts/host_", "scripts/origin_publish.py",
    "scripts/self_heal.py", "dashboard/", "matrix/",
)
FILLER_PREFIXES = ("describe_", "describe_loop_", "describe_spine_")
FILLER_IDS = frozenset({"find_add", "next_bug", "find_fits", "find_clamp"})


def guard_enabled() -> bool:
    return os.getenv("ETHER_GOAL_GUARD", "1") != "0"


def _literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) or (
        isinstance(node, (ast.Tuple, ast.List)) and all(isinstance(e, ast.Constant) for e in node.elts))


def _const_call_assert(test: ast.Assert) -> bool:
    cmp = test.test
    if not isinstance(cmp, ast.Compare) or len(cmp.ops) != 1:
        return False
    left, right = cmp.left, cmp.comparators[0]
    for call, lit in ((left, right), (right, left)):
        if isinstance(call, ast.Call) and not call.args and not call.keywords and _literal(lit):
            return True
    return False


def constant_test(code: str) -> bool:
    """True when every assert is a zero-arg call compared to a literal."""
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return False
    asserts = [n for n in ast.walk(tree) if isinstance(n, ast.Assert)]
    return bool(asserts) and all(_const_call_assert(a) for a in asserts)


def spoiled(prompt: str, symbol: str, current: str = "") -> bool:
    """The prompt holds a `def <symbol>(...)` body that is not the current (broken) code.

    Showing the code that fails is context; showing a new body is the answer."""
    if not prompt or not symbol:
        return False
    name = symbol.split(".")[-1]
    for m in re.finditer(rf"def {re.escape(name)}\s*\([^\n]*\)[^\n]*:\s*\n\s+\S", prompt):
        lines = prompt[m.start():].split("\n")
        block = [lines[0]]
        for line in lines[1:]:
            if line.strip() and not line[:1].isspace():
                break
            block.append(line)
        cur = [l.strip() for l in (current or "").splitlines() if l.strip()]
        if not cur:
            return True
        # Every shown line must already be in the file (a slice may skip lines or
        # cut the last one); a line the file does not have is new code = answer.
        for line in (l.strip() for l in block if l.strip()):
            if not any(line in c for c in cur):
                return True
    return False


def protected(rel: str) -> bool:
    rel = (rel or "").replace("\\", "/")
    return any(rel.startswith(p) for p in PROTECTED_PREFIXES) or "/test_" in rel


def filler_id(goal_id: str) -> bool:
    return goal_id in FILLER_IDS or any(goal_id.startswith(p) for p in FILLER_PREFIXES)


def check(goal: Dict[str, Any], prompt: str = "", current: str = "") -> Dict[str, Any]:
    reasons: List[str] = []
    if filler_id(str(goal.get("id") or "")):
        reasons.append("filler")
    if goal.get("test") and constant_test(str(goal["test"])):
        reasons.append("constant")
    if prompt and spoiled(prompt, str(goal.get("symbol") or ""), current):
        reasons.append("spoiler")
    if goal.get("kind") in ("fix_test", "lint") and protected(str(goal.get("file") or "")):
        reasons.append("self_edit")
    return {"ok": not reasons, "reasons": reasons}
