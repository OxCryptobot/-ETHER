"""Test-or-Cap: ensure code has a minimal executable check before sandbox."""

from __future__ import annotations

import ast
import re
from typing import Tuple


def has_self_check(code: str) -> bool:
    if not code or not code.strip():
        return False
    low = code.lower()
    if "assert " in low or "print(" in low:
        return True
    if re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", code):
        return True
    return False


def _public_funcs(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    names = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            names.append(node.name)
    return names


def ensure_harness(code: str) -> Tuple[str, bool]:
    """Append a minimal print/assert harness if missing. Returns (code, modified)."""
    if has_self_check(code):
        return code, False
    funcs = _public_funcs(code)
    if not funcs:
        # still add a benign print so execution is observable
        return code.rstrip() + "\n\nprint('ok')\n", True
    name = funcs[0]
    # generic safe call attempts
    harness = f"""

# auto harness (test-or-cap)
if __name__ == "__main__" or True:
    try:
        _fn = {name}
        import inspect
        _sig = inspect.signature(_fn)
        _args = []
        for _p in list(_sig.parameters.values())[:3]:
            if _p.default is not inspect.Parameter.empty:
                continue
            _an = _p.name.lower()
            if _an in ("s", "text", "string", "word", "msg", "name"):
                _args.append("test")
            elif _an in ("n", "num", "count", "k", "i", "x", "y", "a", "b"):
                _args.append(2)
            elif _an in ("xs", "arr", "data", "items", "lst", "list"):
                _args.append([1, 2, 3])
            else:
                _args.append(1)
        _out = _fn(*_args)
        print(_out)
    except TypeError:
        try:
            print({name}())
        except Exception as _e:
            print(type(_e).__name__, _e)
    except Exception as _e:
        print(type(_e).__name__, _e)
"""
    return code.rstrip() + harness, True
