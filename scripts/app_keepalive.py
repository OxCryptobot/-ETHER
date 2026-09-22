"""Arm hidden logon keepalive. schtasks /Create, never XML."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

def ensure_keepalive(root: Path) -> Dict[str, Any]:
    try:
        from scripts.self_heal import arm
        return arm()
    except Exception as exc:
        return {"ok": False, "armed": False, "error": type(exc).__name__}
