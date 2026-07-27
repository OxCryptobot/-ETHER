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


def _is_constant_expr(node: ast.expr) -> bool:
    """True if `node` involves no names, calls, or attribute/subscript access.

    Such an expression depends on nothing in the program under test, so its
    value is fixed at parse time and asserting it proves nothing.
    """
    for child in ast.walk(node):
        if isinstance(
            child,
            (ast.Name, ast.Call, ast.Attribute, ast.Subscript, ast.Starred, ast.Await),
        ):
            return False
        if isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
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


def _handler_swallows(handler: ast.ExceptHandler) -> bool:
    """True if this handler catches assertion failures without re-raising."""
    caught = handler.type
    if caught is None:  # bare `except:`
        names: tuple[str, ...] = _SWALLOWING
    else:
        nodes = caught.elts if isinstance(caught, ast.Tuple) else [caught]
        names = tuple(n.id for n in nodes if isinstance(n, ast.Name))
    if not any(name in _SWALLOWING for name in names):
        return False
    # Re-raising still surfaces the failure to the sandbox exit code.
    return not any(isinstance(n, ast.Raise) for n in ast.walk(handler))


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

    if isinstance(node, ast.Try):
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


def count_real_asserts(code: str) -> int:
    """Count assertions in `code` that could actually fail and be observed."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0
    return _count(tree, False)


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
