"""Reject secrets in writes before they hit disk."""
from __future__ import annotations
import re
from typing import Optional

_PATS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)AKIA[0-9A-Z]{16}"),
)

def secret_hit(text: str) -> Optional[str]:
    blob = text or ""
    for pat in _PATS:
        if pat.search(blob):
            return "secret_in_write"
    return None
