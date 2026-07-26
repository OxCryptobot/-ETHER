#!/usr/bin/env python3
"""Map .py files and top-level symbols."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, repo_root, safe_path

SKIP = {".git", ".venv", "venv", "__pycache__", "node_modules", "memory"}


def symbols(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out.append(f"def {node.name}")
        elif isinstance(node, ast.AsyncFunctionDef):
            out.append(f"async def {node.name}")
        elif isinstance(node, ast.ClassDef):
            out.append(f"class {node.name}")
    return out


def main() -> None:
    inp = read_input()
    root = safe_path(inp.get("path", "."), repo_root())
    max_files = int(inp.get("max_files", 200))
    files = []
    for p in root.rglob("*.py"):
        if any(x in SKIP for x in p.parts):
            continue
        files.append({"path": str(p.relative_to(repo_root())).replace("\\", "/"), "symbols": symbols(p)})
        if len(files) >= max_files:
            break
    emit(True, root=str(root), files=files, count=len(files))


if __name__ == "__main__":
    main()
