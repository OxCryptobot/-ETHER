"""Python AST intel. Not an LSP. Honest go-to-def / hover for .py only."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional


def _parse(path: Path) -> Optional[ast.AST]:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def hover(path: str, name: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file() or p.suffix != ".py":
        return {"ok": False, "via": "ast_lite", "error": "not_python"}
    tree = _parse(p)
    if tree is None:
        return {"ok": False, "via": "ast_lite", "error": "parse_fail"}
    hits: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            hits.append(f"def {node.name}(...) @ line {node.lineno}")
        if isinstance(node, ast.ClassDef) and node.name == name:
            hits.append(f"class {node.name} @ line {node.lineno}")
    return {"ok": bool(hits), "via": "ast_lite", "path": str(p), "name": name, "hits": hits[:8]}


def goto_def(path: str, name: str) -> Dict[str, Any]:
    out = hover(path, name)
    out["tool"] = "goto_def"
    return out
