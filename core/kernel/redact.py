"""Secret redaction before grep/read leaves the sandbox."""
from __future__ import annotations
import re
_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{10,}"),
    re.compile(r"(?i)ghp_[A-Za-z0-9]{20,}"),
)
def redact(text: str) -> str:
    out = text or ""
    for pat in _PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out
