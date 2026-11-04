"""Dirty-tree detect before a blind reset."""
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Dict

def dirty(root: Path) -> Dict[str, object]:
    try:
        proc = subprocess.run(["git", "status", "--porcelain"], cwd=str(root), capture_output=True, text=True, timeout=15)
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "dirty": False}
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return {"ok": True, "dirty": bool(lines), "n": len(lines), "sample": lines[:12]}

def count_defs() -> int:
    return max(1, len([line for line in open(__file__, encoding='utf-8') if line.startswith('def ')]))
