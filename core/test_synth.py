"""Property / unit assert synthesis before sandbox (verification density)."""

from __future__ import annotations

import ast
import re
from typing import List, Tuple

from core.assert_audit import count_real_asserts

# Written as an executable statement, not only as a comment, so the "already
# synthesized" guard can be checked on the AST. Comments do not survive
# parsing, so a model that pasted the marker comment could otherwise suppress
# synthesis for its own output.
SYNTH_MARKER = "_ether_synth_asserts"


def _funcs(code: str) -> List[ast.FunctionDef]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    # Only plain functions: an `async def` cannot be called from a synthesized
    # module-level assert, and `assert coro(...) == v` would compare against a
    # coroutine object. core/assert_harness.py exercises those instead.
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]


def has_assert(code: str) -> bool:
    """True when the code already carries a real, observable assertion.

    AST-based. The previous `re.search(r"\\bassert\\b", code)` matched the word
    inside comments and docstrings, so `# TODO: assert the invariant` disabled
    synthesis for the whole file. Tautologies and assertions swallowed by an
    enclosing `except` do not count as existing verification either — see
    core/assert_audit.py.
    """
    return count_real_asserts(code or "") > 0


def _already_synthesized(code: str) -> bool:
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return SYNTH_MARKER in (code or "")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == SYNTH_MARKER:
            return True
    return SYNTH_MARKER in (code or "")


def _literal_prefix(text: str) -> str:
    """Longest leading slice of `text` that is a Python literal, else ""."""
    tokens = text.split()
    for end in range(len(tokens), 0, -1):
        candidate = " ".join(tokens[:end]).rstrip(" ,.;:")
        if not candidate:
            continue
        try:
            ast.literal_eval(candidate)
        except Exception:
            continue
        return candidate
    return ""


def _objective_assert(name: str, objective: str) -> str:
    """`name(args) == value` / `name(args) is value` pulled from the objective.

    This is the only branch here that produces a genuinely falsifiable
    assertion, which is why the objective has to actually reach this module —
    it was hardcoded to "" at the sandbox call site.

    Both sides must be literals and the result must parse. A half-parsed
    fragment such as `assert add(2, 3) == the sum` would otherwise be appended
    to every program and turn correct code into a SyntaxError.
    """
    if not objective:
        return ""
    pat = re.compile(
        rf"(?<![\w.]){re.escape(name)}\s*\(([^()]*)\)\s*(==|is not|is)\s+([^\n#;]+)"
    )
    for m in pat.finditer(objective):
        args, op, raw = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        value = _literal_prefix(raw)
        if not value:
            continue
        stmt = f"assert {name}({args}) {op} {value}"
        try:
            node = ast.parse(stmt).body[0]
        except SyntaxError:
            continue
        if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
            continue
        call = node.test.left
        if not isinstance(call, ast.Call) or call.keywords:
            continue
        try:
            for arg in call.args:
                ast.literal_eval(arg)
        except Exception:
            continue
        return stmt
    return ""


def synthesize_asserts(code: str, objective: str = "") -> Tuple[str, bool]:
    """If no asserts, append best-effort checks from AST + objective literals.

    Returns (code, modified).
    """
    if not code or not code.strip():
        return code, False
    if has_assert(code):
        return code, False
    if _already_synthesized(code):
        return code, False

    funcs = _funcs(code)
    if not funcs:
        return code, False

    lines: List[str] = ["", "# synthesized asserts (test_synth)", f"{SYNTH_MARKER} = True"]
    obj = objective or ""

    for fn in funcs[:3]:
        name = fn.name

        # Objective-derived expectations first: they are checked against the
        # real implementation and can fail. The boolean-name heuristics below
        # used to shadow this branch for any `is_*`/`has_*` function.
        derived = _objective_assert(name, obj)
        if derived:
            lines.append(derived)
            continue

        # boolean-ish names
        if re.search(r"\b(is_|has_|can_|check_)", name) or name in {"is_even", "is_prime", "is_palindrome"}:
            # `assert callable(f)` is true for every function ever defined, so
            # it was counted as a real test and handed any output containing an
            # is_/has_/can_/check_ function a free verification score of 1.000.
            if name == "is_even":
                lines.append(f"assert {name}(2) is True")
                lines.append(f"assert {name}(3) is False")
            elif name == "is_prime":
                lines.append(f"assert {name}(2) is True")
                lines.append(f"assert {name}(4) is False")
            elif name == "is_palindrome":
                lines.append(f"assert {name}('aba') is True")
            else:
                lines.append(f"assert {name}(1) in (True, False) or {name}(1) is not None")
            continue

        # Nothing falsifiable can be derived for this function. The previous
        # fallback guessed `2` for every unrecognised parameter name and
        # emitted `_r = f(2)` followed by `assert _r is not None or _r is None
        # or True`. The assertion is a tautology (assert_audit counts it as
        # zero), but the CALL ran at module level and was not tolerant of a
        # bad guess: `def total(values): return sum(values)` — a correct
        # solution — crashed with "'int' object is not iterable" and was
        # scored as a failing program. Exercising the code is the harness's
        # job (core/assert_harness.py), which tries several argument shapes
        # and only fails when none of them work.
        continue

    if len(lines) <= 3:
        return code, False

    block = "\n".join(lines) + "\n"
    return code.rstrip() + "\n" + block, True
