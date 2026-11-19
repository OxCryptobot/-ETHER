"""Incremental symbol index for the 4B retrieve step."""
from __future__ import annotations
import ast, json, time
from pathlib import Path
from typing import Any, Dict, Iterable, List

SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "memory", "dist", "build"}

def _iter_py(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        if any(part in SKIP for part in p.parts):
            continue
        yield p

def _symbols(path: Path) -> List[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return []
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names[:80]

def build_index(root: Path) -> Dict[str, Any]:
    root = Path(root)
    files: List[Dict[str, Any]] = []
    for p in list(_iter_py(root))[:400]:
        rel = str(p.relative_to(root)).replace("\\", "/")
        try:
            st = p.stat()
        except OSError:
            continue
        files.append({"path": rel, "mtime": int(st.st_mtime), "size": int(st.st_size), "symbols": _symbols(p)})
    return {"ts": time.time(), "n": len(files), "files": files}

def query_index(index: Dict[str, Any], q: str, *, k: int = 8) -> List[Dict[str, Any]]:
    terms = {t.lower() for t in (q or "").replace("/", " ").split() if len(t) > 2}
    scored: List[tuple[int, Dict[str, Any]]] = []
    for row in index.get("files") or []:
        blob = ((row.get("path") or "") + " " + " ".join(row.get("symbols") or [])).lower()
        hits = sum(1 for t in terms if t in blob)
        if hits:
            scored.append((hits, row))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:k]]

def format_hits(hits: List[Dict[str, Any]], *, max_chars: int = 1200) -> str:
    lines = []
    used = 0
    for row in hits:
        line = f"{row.get('path')} :: {', '.join((row.get('symbols') or [])[:8])}"
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)

def save_index(root: Path, dest: Path | None = None) -> Path:
    dest = Path(dest or (Path(root) / "artifacts" / "symbol_index.json"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(build_index(root), indent=2) + "\n", encoding="utf-8")
    return dest
