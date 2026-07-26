#!/usr/bin/env python3
"""Fail if imports outside allowlist appear in code."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, safe_path

DEFAULT_ALLOW = {
    "math", "json", "re", "sys", "os", "pathlib", "typing", "dataclasses",
    "datetime", "collections", "itertools", "functools", "uuid", "hashlib",
    "tempfile", "subprocess", "ast", "textwrap", "copy", "enum",
}


def main() -> None:
    inp = read_input()
    text = inp.get("text")
    if not text and inp.get("path"):
        text = safe_path(inp["path"]).read_text(encoding="utf-8", errors="ignore")
    if not text:
        emit(False, error="text or path required")
    allow = set(inp.get("allowlist") or DEFAULT_ALLOW)
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        emit(False, error=f"syntax: {e}")
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top not in allow:
                    bad.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top not in allow:
                    bad.append(node.module)
    emit(len(bad) == 0, violations=bad, allowlist=sorted(allow))


if __name__ == "__main__":
    main()
