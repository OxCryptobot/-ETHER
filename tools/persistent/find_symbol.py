#!/usr/bin/env python3
"""Locate def/class by name under repo."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, repo_root

SKIP = {".git", ".venv", "venv", "__pycache__", "memory"}


def main() -> None:
    inp = read_input()
    name = inp.get("name") or inp.get("symbol")
    if not name:
        emit(False, error="name required")
    hits = []
    for p in repo_root().rglob("*.py"):
        if any(x in SKIP for x in p.parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                hits.append(
                    {
                        "path": str(p.relative_to(repo_root())).replace("\\", "/"),
                        "lineno": getattr(node, "lineno", None),
                        "kind": type(node).__name__,
                    }
                )
    emit(True, name=name, hits=hits, count=len(hits))


if __name__ == "__main__":
    main()
