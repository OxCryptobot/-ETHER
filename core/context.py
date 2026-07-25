"""Multi-file workspace context for coding prompts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from core.chunking import chunk_file

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    "memory",
    "dist",
    "build",
}


def gather_workspace_context(
    root: Optional[Path] = None,
    query: str = "",
    max_files: int = 8,
    max_chars: int = 4000,
) -> str:
    """Collect relevant local file snippets for the coding prompt.

    Lightweight: no Qdrant required. Scores by path/name keyword overlap.
    """
    root = root or Path.cwd()
    q = set(re_tokens(query))
    candidates: List[tuple[float, Path]] = []

    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        score = _score(path, q)
        candidates.append((score, path))

    candidates.sort(key=lambda x: x[0], reverse=True)
    selected = [p for s, p in candidates[:max_files] if s > 0] or [p for _, p in candidates[:3]]

    parts: List[str] = []
    total = 0
    for path in selected:
        chunks = chunk_file(path, max_chars=800)
        if not chunks:
            continue
        body = chunks[0]["text"]
        snippet = f"# file: {path.as_posix()}\n{body}\n"
        if total + len(snippet) > max_chars:
            break
        parts.append(snippet)
        total += len(snippet)

    return "\n".join(parts)


def re_tokens(text: str) -> List[str]:
    import re

    return [t for t in re.findall(r"[a-zA-Z_]{3,}", text.lower()) if t not in {"the", "and", "for", "with"}]


def _score(path: Path, qtokens: set[str]) -> float:
    if not qtokens:
        return 0.1
    name = path.stem.lower()
    blob = f"{name} {' '.join(path.parts)}".lower()
    hits = sum(1 for t in qtokens if t in blob)
    return float(hits)


def context_enabled() -> bool:
    return os.getenv("ETHER_USE_CONTEXT", "1") == "1"
