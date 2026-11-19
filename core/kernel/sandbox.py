"""Job filesystem jail. Writes stay inside workspace."""
from __future__ import annotations
from pathlib import Path

BLOCKED = {".git", ".venv", "venv", "memory", "node_modules", "__pycache__"}

def resolve_in(root: Path, rel: str) -> Path:
    root = Path(root).resolve()
    raw = (rel or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise ValueError("absolute path refused")
    target = (root / raw).resolve()
    target.relative_to(root)
    if any(part.lower() in BLOCKED for part in target.parts):
        raise ValueError("blocked segment")
    return target

def allowed(root: Path, rel: str) -> bool:
    try:
        resolve_in(root, rel)
        return True
    except (ValueError, OSError):
        return False
