"""Repo contract + tool constitution for every job."""
from __future__ import annotations
from pathlib import Path
from core.kernel.constitution import TOOL_CONSTITUTION

def load_ether_md(root: Path) -> str:
    p = Path(root) / "ETHER.md"
    if not p.is_file():
        return TOOL_CONSTITUTION
    try:
        return p.read_text(encoding="utf-8")[:1200]
    except OSError:
        return TOOL_CONSTITUTION

def inject(root: Path) -> str:
    body = load_ether_md(root).strip()
    if TOOL_CONSTITUTION.strip() in body:
        return body[:1600]
    return (TOOL_CONSTITUTION.strip() + "\n\n" + body)[:1600]
