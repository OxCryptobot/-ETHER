"""Symbol / file index v0 (Phase 2.4).

Local-first. No vector DB. AST top-level defs/classes + path tokens ranked by
query overlap. Opt-in via ETHER_SYMBOL_INDEX=1 when used from context gather.
Standalone callers always work; default pipeline behavior is unchanged unless
the env flag is set.
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "memory",
    ".pytest_cache",
    "artifacts",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
}


def symbol_index_enabled() -> bool:
    return os.getenv("ETHER_SYMBOL_INDEX", "0") == "1"


def _tokenize(text: str) -> Set[str]:
    return {
        t
        for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", (text or "").lower())
        if len(t) > 2
    }


@dataclass
class FileSymbols:
    path: str
    symbols: List[str] = field(default_factory=list)

    @property
    def blob(self) -> str:
        return self.path + " " + " ".join(self.symbols)


def extract_symbols(source: str) -> List[str]:
    """Top-level function/class names from Python source. Never raises."""
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return []
    out: List[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(node.name)
        elif isinstance(node, ast.ClassDef):
            out.append(node.name)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(f"{node.name}.{child.name}")
    return out


def index_tree(
    root: Path,
    *,
    max_files: int = 400,
    skip_dirs: Optional[Set[str]] = None,
) -> List[FileSymbols]:
    """Walk root for .py files and extract symbols. Deterministic order."""
    root = Path(root).resolve()
    skip = skip_dirs if skip_dirs is not None else SKIP_DIRS
    entries: List[FileSymbols] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in skip for part in path.parts):
            continue
        try:
            rel = str(path.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        entries.append(FileSymbols(path=rel, symbols=extract_symbols(text)))
        if len(entries) >= max_files:
            break
    return entries


def rank(
    entries: Sequence[FileSymbols],
    query: str,
    *,
    k: int = 12,
) -> List[Tuple[float, FileSymbols]]:
    """Score entries by token overlap with query. Higher is better."""
    q = _tokenize(query)
    if not q:
        return [(0.0, e) for e in list(entries)[:k]]
    scored: List[Tuple[float, FileSymbols]] = []
    for e in entries:
        blob = _tokenize(e.blob)
        overlap = len(q & blob)
        if overlap == 0:
            continue
        path_bonus = 0.5 if any(t in e.path.lower() for t in q) else 0.0
        score = overlap + path_bonus
        scored.append((score, e))
    scored.sort(key=lambda x: (-x[0], x[1].path))
    return scored[:k]


def format_block(
    query: str,
    *,
    root: Optional[Path] = None,
    k: int = 8,
    max_chars: int = 1800,
) -> str:
    """Prompt-ready symbol map ranked by query. Empty on miss."""
    root = Path(root or ROOT).resolve()
    entries = index_tree(root)
    hits = rank(entries, query, k=k)
    if not hits:
        return ""
    lines: List[str] = []
    used = 0
    for score, e in hits:
        syms = ", ".join(e.symbols[:12]) if e.symbols else "(no top-level symbols)"
        line = f"{e.path}: {syms}"
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def search(
    query: str,
    *,
    root: Optional[Path] = None,
    k: int = 12,
) -> List[Dict[str, object]]:
    """Structured search API for tools / tests."""
    root = Path(root or ROOT).resolve()
    entries = index_tree(root)
    return [
        {"score": score, "path": e.path, "symbols": list(e.symbols)}
        for score, e in rank(entries, query, k=k)
    ]
