"""Ignore rules for retrieve and grep."""
from __future__ import annotations
from pathlib import Path

SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "memory", "dist", "build", "_graveyard"}

def ignored(path: Path | str) -> bool:
    parts = Path(str(path)).parts
    return any(p in SKIP for p in parts)
