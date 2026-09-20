"""Typed parse fail. _retry is not a tool."""
from __future__ import annotations
from typing import Any, Dict

def parse_fail(reason: str = "unparseable") -> Dict[str, Any]:
    return {"ok": False, "error": "parse_fail", "reason": reason, "tool": None}
