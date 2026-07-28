"""Honest assertion accounting for sandbox verification.

The original counter regexed the raw source for the token `assert` and regexed
stdout for `N passed`. Both are trivially forgeable. An audit confirmed that a
no-op function, an assert inside a comment, a *false* assert swallowed by
`except AssertionError`, and a bare `print("42 passed")` all scored a perfect
verification of 1.000 — while honest code that reported a real failure scored
0.26. The metric rewarded concealment.

This module counts only assertions that could actually have failed and been
observed:

  * parsed from the AST, so comments and string literals never count
  * statically-unreachable branches (`if False:`) are skipped
  * assertions whose failure is swallowed by an enclosing `try` are skipped
  * tautologies are skipped (`assert True`, `assert 1 == 1`,
    `assert _r is not None or _r is None or True`)

Known limitation: an assertion inside a function body is still counted even if
the function is never called. Resolving call graphs statically is unreliable,
so this over-counts rather than silently under-reporting. Callers that need a
stronger signal should grade against held-out tests the generator never saw.
"""

from __future__ import annotations

import ast
from typing import Optional

# Handler types that make an enclosing assertion failure invisible.
_SWALLOWING = ("AssertionError", "Exception", "BaseException")

_SENTINEL = object()


def _literal(node: ast.expr) -> object:
    """Constant-fold `node`, or return the sentinel if it isn't a literal."""
    try:
        return ast.literal_eval(node)
    except Exception:
        return _SENTINEL


def _const_truthy(node: ast.expr) -> Optional[bool]:
    """Truth value of a constant expression, or None if not constant."""
    value = _literal(node)
    return None if value is _SENTINEL else bool(value)


def _is_none_tautology(node: ast.BoolOp) -> bool:
    """Detect `x is None or x is not None` over the same target."""
    seen: set[tuple[str, bool]] = set()
    for value in node.values:
        if (
            isinstance(value, ast.Compare)
            and len(value.ops) == 1
            and isinstance(value.ops[0], (ast.Is, ast.IsNot))
            and len(value.comparators) == 1
            and isinstance(value.comparators[0], ast.Constant)
            and value.comparators[0].value is None
        ):
            seen.add((ast.dump(value.left), isinstance(value.ops[0], ast.IsNot)))
    return any((target, True) in seen and (target, False) in seen for target, _ in seen)


# Bounds for constant folding. `assert 9**9**9 == 1` inside a never-called
# function is valid Python that costs nothing to run, but folding it on the
# HOST — outside the sandbox, since counting happens in-process — hung for
# minutes and allocated gigabytes. Model-authored code reaches this path, so
# it must be bounded rather than merely correct.
_MAX_CONST_NODES = 60
_MAX_INT_LITERAL = 10**12
_MAX_STR_LITERAL = 4096


def _is_constant_expr(node: ast.expr) -> bool:
    """True if `node` is safely constant-foldable.

    Requires no names, calls, or attribute/subscript access — so nothing from
    the program under test can execute — and additionally bounds size and
    forbids exponentiation, which is the cheap way to make folding expensive.
    """
    nodes = 0
    for child in ast.walk(node):
        nodes += 1
        if nodes > _MAX_CONST_NODES:
            return False
        if isinstance(
            child,
            (ast.Name, ast.Call, ast.Attribute, ast.Subscript, ast.Starred, ast.Await),
        ):
            return False
        if isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            return False
        # `**` turns tiny source into astronomically large values; `*` can do
        # the same for sequences (`'a' * 10**9`).
        if isinstance(child, ast.BinOp) and isinstance(child.op, (ast.Pow, ast.Mult)):
            return False
        if isinstance(child, ast.Constant):
            value = child.value
            if isinstance(value, int) and not isinstance(value, bool):
                if abs(value) > _MAX_INT_LITERAL:
                    return False
            elif isinstance(value, (str, bytes)) and len(value) > _MAX_STR_LITERAL:
                return False
    return True


def _static_truth(node: ast.expr) -> Optional[bool]:
    """Evaluate a wholly-constant expression, or return None.

    `ast.literal_eval` refuses `1 + 1` on modern Python, so a purely literal
    comparison like `assert 1 + 1 == 2` would otherwise be counted as a real
    test. Evaluation is gated on `_is_constant_expr`, so there are no names,
    calls or attribute lookups to resolve — nothing from the program under
    test can execute here.
    """
    if not _is_constant_expr(node):
        return None
    try:
        return bool(eval(compile(ast.Expression(body=node), "<const>", "eval"), {"__builtins__": {}}, {}))
    except Exception:
        return None


def _is_tautology(test: ast.expr) -> bool:
    """True when the assertion's test can never evaluate False."""
    if _const_truthy(test) is True:
        return True
    if _static_truth(test) is True:
        return True

    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        # `... or True` — exactly the shape core/test_synth.py injects.
        if any(_const_truthy(v) is True for v in test.values):
            return True
        if _is_none_tautology(test):
            return True

    # Both sides constant: `assert 1 == 1`, `assert 2 != 3`.
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        left, right = _literal(test.left), _literal(test.comparators[0])
        if left is not _SENTINEL and right is not _SENTINEL:
            op = test.ops[0]
            try:
                if isinstance(op, ast.Eq):
                    return bool(left == right)
                if isinstance(op, ast.NotEq):
                    return bool(left != right)
                if isinstance(op, ast.Is):
                    return left is right
                if isinstance(op, ast.IsNot):
                    return left is not right
            except Exception:
                return False
    return False


def _exc_name(node: ast.expr) -> str:
    """Last component of an exception reference.

    `except builtins.AssertionError:` is an ast.Attribute, not an ast.Name, so
    matching only on Name let a dotted spelling swallow assertions unnoticed.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _handler_swallows(handler: ast.ExceptHandler) -> bool:
    """True if this handler catches assertion failures without re-raising."""
    caught = handler.type
    if caught is None:  # bare `except:`
        names: tuple[str, ...] = _SWALLOWING
    else:
        nodes = caught.elts if isinstance(caught, ast.Tuple) else [caught]
        names = tuple(_exc_name(n) for n in nodes)
    if not any(name in _SWALLOWING for name in names):
        return False
    # Re-raising surfaces the failure — but only if it is actually reachable.
    # `ast.walk` counted a `raise` sitting in dead code inside the handler.
    return not any(isinstance(stmt, ast.Raise) for stmt in _reachable_stmts(handler.body))


def _reachable_stmts(body: list) -> list:
    """Flatten statements, skipping statically-dead branches."""
    out = []
    for stmt in body:
        if isinstance(stmt, ast.If):
            cond = _const_truthy(stmt.test)
            if cond is not False:
                out.extend(_reachable_stmts(stmt.body))
            if cond is not True:
                out.extend(_reachable_stmts(stmt.orelse))
            continue
        if isinstance(stmt, ast.While) and _const_truthy(stmt.test) is False:
            continue
        out.append(stmt)
        for attr in ("body", "orelse", "finalbody"):
            nested = getattr(stmt, attr, None)
            if isinstance(nested, list) and not isinstance(stmt, ast.If):
                out.extend(_reachable_stmts(nested))
    return out


def _suppresses_assertions(node: ast.With) -> bool:
    """True for `with contextlib.suppress(AssertionError):` and friends."""
    for item in node.items:
        call = item.context_expr
        if not isinstance(call, ast.Call):
            continue
        if _exc_name(call.func) != "suppress":
            continue
        if any(_exc_name(a) in _SWALLOWING for a in call.args):
            return True
    return False


def _count(node: ast.AST, swallowed: bool) -> int:
    """Count observable assertions in `node`, including `node` itself."""
    if isinstance(node, ast.Assert):
        return 0 if (swallowed or _is_tautology(node.test)) else 1

    total = 0

    if isinstance(node, ast.If):
        cond = _const_truthy(node.test)
        if cond is not False:  # `if False:` body is dead
            for stmt in node.body:
                total += _count(stmt, swallowed)
        if cond is not True:  # `if True:` else-branch is dead
            for stmt in node.orelse:
                total += _count(stmt, swallowed)
        return total

    if isinstance(node, ast.While):
        if _const_truthy(node.test) is False:
            return 0
        for group in (node.body, node.orelse):
            for stmt in group:
                total += _count(stmt, swallowed)
        return total

    # `for _ in []:` / `for _ in ():` never executes its body.
    if isinstance(node, ast.For):
        iterable = _literal(node.iter)
        if iterable is not _SENTINEL:
            try:
                if len(iterable) == 0:  # type: ignore[arg-type]
                    return 0
            except TypeError:
                pass
        for group in (node.body, node.orelse):
            for stmt in group:
                total += _count(stmt, swallowed)
        return total

    # `with contextlib.suppress(AssertionError):` swallows just like except.
    if isinstance(node, ast.With):
        inner = swallowed or _suppresses_assertions(node)
        for stmt in node.body:
            total += _count(stmt, inner)
        return total

    # ast.Try covers `except*` too on 3.11+ via ast.TryStar, which previously
    # fell through to the generic branch and was never treated as swallowing.
    try_types: tuple = (ast.Try, getattr(ast, "TryStar", ast.Try))
    if isinstance(node, try_types):
        swallows = any(_handler_swallows(h) for h in node.handlers)
        for stmt in node.body:
            total += _count(stmt, swallowed or swallows)
        for handler in node.handlers:
            for stmt in handler.body:
                total += _count(stmt, swallowed)
        for group in (node.orelse, node.finalbody):
            for stmt in group:
                total += _count(stmt, swallowed)
        return total

    for child in ast.iter_child_nodes(node):
        total += _count(child, swallowed)
    return total


def _called_names(tree: ast.AST) -> set:
    """Function names invoked anywhere in the module."""
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    return called


def count_real_asserts(code: str) -> int:
    """Count assertions in `code` that could actually fail and be observed.

    Assertions inside a function nobody calls never execute, so they are not
    evidence. That was the last hole in this counter: a wrong implementation
    carrying `def test_add(): assert add(1,1) == 2` scored total_tests=3 and
    confidence 1.000 while `add` returned `a - b`, because pytest-style test
    functions are defined and never invoked when the file is run as a script.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0

    called = _called_names(tree)
    total = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Count a function's assertions only if something calls it.
            if node.name in called:
                total += _count(node, False)
            continue
        if isinstance(node, ast.ClassDef):
            # Methods need an instance; treat as reachable only if the class is
            # instantiated somewhere.
            if node.name in called:
                total += _count(node, False)
            continue
        total += _count(node, False)
    return total


def uses_test_runner(code: str) -> bool:
    """True if `code` actually imports pytest or unittest.

    Counts reported on stdout (`N passed`, `Ran N tests`) are only meaningful
    when a real runner produced them; otherwise `print("42 passed")`
    manufactures a perfect score.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] in ("pytest", "unittest") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in ("pytest", "unittest"):
                return True
    return False
