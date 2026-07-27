"""Test-or-Cap: ensure code has a minimal executable check before sandbox.

Two properties this module must have, both of which it previously lacked:

  * A crash must be visible. The generated harness used to wrap the call in
    `except Exception as _e: print(type(_e).__name__, _e)`, so a function that
    raised on every input printed the exception and exited 0 — scoring
    `execution_score 1.0` on code that does not work.
  * Everything callable must actually be called. `_public_funcs` only matched
    top-level `ast.FunctionDef`, so class-based, async, and `_private`-only
    solutions were never invoked; they received a bare `print('ok')` and also
    scored 1.0.

Detection is AST-based throughout. The old `"assert " in code or "print(" in
code` substring test treated `# TODO: assert the invariant` in a comment, or
the word `print(` inside a docstring, as an existing self-check and suppressed
the harness entirely.
"""

from __future__ import annotations

import ast
from typing import List, Optional, Tuple

from core.assert_audit import count_real_asserts

# Emitted when the module contains nothing that can be called. Distinguishable
# on stdout from a real result, unlike the old bare `print('ok')` which was
# indistinguishable from a successful run.
NO_CALLABLE_MARKER = "__ETHER_NO_CALLABLE__"

# Emitted when everything callable refused every argument shape the harness
# could guess. Neither a pass nor a proof of a defect — say so rather than
# picking one.
UNCALLABLE_MARKER = "__ETHER_UNCALLABLE__"

HARNESS_MARKER = "# auto harness (test-or-cap)"

# How many top-level definitions the harness exercises.
_MAX_TARGETS = 3


def _parse(code: str) -> Optional[ast.Module]:
    try:
        return ast.parse(code or "")
    except SyntaxError:
        return None


def _is_main_guard(test: ast.expr) -> bool:
    """True for `if __name__ == "__main__":`."""
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.ops[0], (ast.Eq, ast.Is)):
        return False
    left, right = test.left, test.comparators[0]
    if isinstance(left, ast.Name) and left.id == "__name__":
        return isinstance(right, ast.Constant) and right.value == "__main__"
    if isinstance(right, ast.Name) and right.id == "__name__":
        return isinstance(left, ast.Constant) and left.value == "__main__"
    return False


def has_self_check(code: str) -> bool:
    """True when the module already executes and observes something.

    AST-based on purpose (see the module docstring): a mention of `assert` or
    `print(` in a comment or docstring is not a self-check.
    """
    if not code or not code.strip():
        return False
    tree = _parse(code)
    if tree is None:
        return False
    if count_real_asserts(code) > 0:
        return True
    for node in tree.body:
        if isinstance(node, ast.If) and _is_main_guard(node.test):
            return True
        # A bare top-level call (`print(...)`, `main()`, `solve(1)`) means the
        # module already runs something when imported.
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return True
    return False


def _public_funcs(code: str) -> List[str]:
    """Names of top-level public functions (sync or async).

    Kept for callers that only want plain functions; `_call_targets` is what
    the harness uses.
    """
    tree = _parse(code)
    if tree is None:
        return []
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]


def _call_targets(code: str) -> List[str]:
    """Top-level definitions worth invoking: functions, async functions, classes.

    Public names win; if a module only defines `_private` helpers those are
    used instead, because "nothing public" is not the same as "nothing to run"
    and silently skipping them is how a broken `_solve` scored a clean pass.
    """
    tree = _parse(code)
    if tree is None:
        return []
    public: List[str] = []
    private: List[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            (private if node.name.startswith("_") else public).append(node.name)
    names = public or private
    return names[:_MAX_TARGETS]


# The runtime half of the harness. Appended to the model's code, so every name
# is `__ether_`-prefixed to avoid colliding with it.
#
# Failure policy. The exception is re-raised — making the process exit non-zero
# — when the failure is attributable to the code rather than to the harness's
# argument guessing:
#
#   * the call needed no arguments at all and still raised; or
#   * every candidate argument shape produced the *same* exception type and
#     message. A function that raises unconditionally fails identically for
#     `2`, `"test"`, `[1, 2, 3]` and `{"a": 1}`; a correct function that the
#     harness simply called wrongly fails differently for each ("'int' object
#     is not iterable", "string indices must be integers", ...).
#
# Otherwise the evidence is genuinely ambiguous — `def names(rows): return
# [r["name"] for r in rows]` cannot be called without a domain object — and
# _UNCALLABLE_MARKER is printed instead of inventing either verdict.
_HARNESS_BODY = '''

# auto harness (test-or-cap)
def __ether_harness():
    import inspect

    __ether_targets = __ETHER_TARGETS__
    __ether_globals = globals()

    def __ether_opts(param):
        n = (param.name or "").lower()
        out = []
        ann = param.annotation
        if ann is not inspect.Parameter.empty:
            a = getattr(ann, "__name__", str(ann)).lower()
            if "bool" in a:
                out.append(True)
            elif "int" in a:
                out.append(2)
            elif "float" in a:
                out.append(2.0)
            elif "str" in a:
                out.append("test")
            elif "dict" in a or "mapping" in a:
                out.append({"a": 1})
            elif "list" in a or "sequence" in a or "iterable" in a or "tuple" in a:
                out.append([1, 2, 3])
        if n in ("s", "text", "string", "word", "msg", "message", "name", "sentence", "line"):
            out.append("test")
        elif n in ("n", "num", "number", "count", "k", "i", "j", "x", "y", "a", "b", "size", "limit"):
            out.append(2)
        elif n in ("xs", "arr", "data", "items", "lst", "list", "nums", "numbers", "values", "seq"):
            out.append([1, 2, 3])
        elif n in ("rows", "records", "entries", "table"):
            out.append([{"name": "test", "value": 1}])
        out.extend(
            [2, "test", [1, 2, 3], 2.0, {"a": 1}, [{"name": "test", "value": 1}], True, None]
        )
        return out

    def __ether_argsets(fn):
        """(list of positional arg tuples, whether any argument was guessed)."""
        try:
            params = [
                p
                for p in inspect.signature(fn).parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                and p.default is p.empty
            ]
        except (TypeError, ValueError):
            return [()], True
        if not params:
            return [()], False
        cols = [__ether_opts(p) for p in params]
        sets = []
        for i in range(min(8, max(len(c) for c in cols))):
            sets.append(tuple(c[i] if i < len(c) else c[-1] for c in cols))
        return sets, True

    def __ether_invoke(fn):
        """(ok, value, first_error, fatal)."""
        sets, guessed = __ether_argsets(fn)
        errors = []
        for args in sets:
            try:
                out = fn(*args)
                if inspect.iscoroutine(out):
                    import asyncio

                    out = asyncio.run(out)
                return True, out, None, False
            except Exception as exc:
                errors.append(exc)
        if not errors:
            return False, None, None, False
        if not guessed:
            # No arguments to get wrong: the code crashed on its own.
            return False, None, errors[0], True
        shapes = set()
        for exc in errors:
            shapes.add((type(exc).__name__, str(exc)))
        return False, None, errors[0], len(errors) > 1 and len(shapes) == 1

    def __ether_exercise(name):
        obj = __ether_globals.get(name)
        if obj is None:
            return None
        if isinstance(obj, type):
            ok, inst, err, fatal = __ether_invoke(obj)
            if not ok:
                return (False, err, fatal)
            methods = [
                m
                for m in vars(obj)
                if not m.startswith("_") and callable(getattr(obj, m, None))
            ]
            if not methods:
                print(inst)
                return (True, None, False)
            mok, mval, merr, mfatal = __ether_invoke(getattr(inst, methods[0]))
            if mok:
                print(mval)
                return (True, None, False)
            return (False, merr, mfatal)
        if callable(obj):
            ok, val, err, fatal = __ether_invoke(obj)
            if ok:
                print(val)
                return (True, None, False)
            return (False, err, fatal)
        return None

    results = []
    for __ether_name in __ether_targets:
        r = __ether_exercise(__ether_name)
        if r is not None:
            results.append(r)

    if not results:
        print("__ETHER_NO_CALLABLE_MARKER__")
        return

    for r in results:
        if not r[0] and r[2] and r[1] is not None:
            raise r[1]
    if not any(r[0] for r in results):
        print("__ETHER_UNCALLABLE_MARKER__")


__ether_harness()
'''


def ensure_harness(code: str) -> Tuple[str, bool]:
    """Append a minimal executable harness if missing. Returns (code, modified)."""
    if has_self_check(code):
        return code, False
    targets = _call_targets(code)
    if not targets:
        # Nothing callable. Emit a marker that is distinguishable from a real
        # result instead of `print('ok')`, which read as a successful run.
        return code.rstrip() + f"\n\nprint({NO_CALLABLE_MARKER!r})\n", True
    harness = (
        _HARNESS_BODY.replace("__ETHER_TARGETS__", repr(targets))
        .replace('"__ETHER_NO_CALLABLE_MARKER__"', repr(NO_CALLABLE_MARKER))
        .replace('"__ETHER_UNCALLABLE_MARKER__"', repr(UNCALLABLE_MARKER))
    )
    return code.rstrip() + harness, True
