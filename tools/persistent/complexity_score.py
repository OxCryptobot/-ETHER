#!/usr/bin/env python3
"""Simple complexity metrics for a Python file or snippet."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, safe_path


def main() -> None:
    inp = read_input()
    text = inp.get("text")
    if not text and inp.get("path"):
        text = safe_path(inp["path"]).read_text(encoding="utf-8", errors="ignore")
    if not text:
        emit(False, error="text or path required")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    try:
        tree = ast.parse(text)
        funcs = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree))
        classes = sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree))
        branches = sum(isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler)) for n in ast.walk(tree))
    except SyntaxError:
        funcs = classes = branches = -1
    score = round(min(1.0, (branches + funcs) / max(10, len(lines))), 3) if lines else 0.0
    emit(True, loc=len(lines), functions=funcs, classes=classes, branches=branches, score=score)


if __name__ == "__main__":
    main()
