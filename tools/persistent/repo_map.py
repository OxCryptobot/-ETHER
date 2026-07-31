#!/usr/bin/env python3
"""Map .py files and top-level symbols; rank by optional query."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, repo_root, safe_path

SKIP = {".git", ".venv", "venv", "__pycache__", "node_modules", "memory", ".pytest_cache"}


def symbols(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            doc = ast.get_docstring(node) or ""
            out.append(f"{prefix} {node.name}" + (f" — {doc.split(chr(10))[0][:80]}" if doc else ""))
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ""
            out.append(f"class {node.name}" + (f" — {doc.split(chr(10))[0][:80]}" if doc else ""))
    return out


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_./\\-]{3,}", (text or "").lower()) if len(t) > 2}


def main() -> None:
    inp = read_input()
    root = safe_path(inp.get("path", "."), repo_root())
    max_files = int(inp.get("max_files", 200))
    query = str(inp.get("query") or inp.get("objective") or "")
    qtok = _tokens(query)

    scored: list[tuple[float, dict]] = []
    for p in root.rglob("*.py"):
        if any(x in SKIP for x in p.parts):
            continue
        rel = str(p.relative_to(repo_root())).replace("\\", "/")
        syms = symbols(p)
        entry = {"path": rel, "symbols": syms}
        if qtok:
            blob = _tokens(rel + " " + " ".join(syms))
            score = len(qtok & blob) / max(1, len(qtok))
            # hard boost exact path mentions (core/patterns.py)
            if any(t in rel.lower() for t in qtok if "/" in t or t.endswith(".py")):
                score += 1.0
            if any(t in rel.lower() for t in qtok):
                score += 0.25
        else:
            score = 0.0
        scored.append((score, entry))

    if qtok:
        scored.sort(key=lambda x: (-x[0], x[1]["path"]))
    else:
        scored.sort(key=lambda x: x[1]["path"])

    files = [e for _, e in scored[:max_files]]
    emit(True, root=str(root), files=files, count=len(files), query=query[:200])


if __name__ == "__main__":
    main()
