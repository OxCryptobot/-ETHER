#!/usr/bin/env python3
"""Generate pytest stubs from function names in code."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input


def main() -> None:
    inp = read_input()
    code = inp.get("code") or ""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        emit(False, error=str(e))
    names = [
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")
    ]
    lines = ["import pytest", ""]
    for name in names:
        lines += [f"def test_{name}():", f"    # TODO: call {name}(...)\n    assert True", ""]
    emit(True, functions=names, tests="\n".join(lines))


if __name__ == "__main__":
    main()
