"""Cheap language detect from repo markers. Not 'it's Python'."""
from __future__ import annotations
from pathlib import Path
from typing import List

MARKERS = (
    ("python", ("pyproject.toml", "setup.py", "requirements.txt")),
    ("node", ("package.json", "package-lock.json", "pnpm-lock.yaml")),
    ("go", ("go.mod",)),
    ("rust", ("Cargo.toml",)),
)

def detect(root: Path) -> List[str]:
    found: List[str] = []
    base = Path(root)
    for name, files in MARKERS:
        if any((base / f).is_file() for f in files):
            found.append(name)
    return found or ["unknown"]
