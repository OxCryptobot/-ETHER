#!/usr/bin/env python3
"""Scan text/code for likely secrets. JSON in/out. No network."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, safe_path

PATTERNS = [
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_token", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"][^'\"]{12,}")),
    ("private_key", re.compile(r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
]


def main() -> None:
    inp = read_input()
    text = inp.get("text")
    if not text and inp.get("path"):
        text = safe_path(inp["path"]).read_text(encoding="utf-8", errors="ignore")
    if text is None:
        emit(False, error="provide text or path")
    findings = []
    for name, rx in PATTERNS:
        for m in rx.finditer(text):
            findings.append({"rule": name, "span": [m.start(), m.end()]})
    emit(True, findings=findings, count=len(findings), clean=len(findings) == 0)


if __name__ == "__main__":
    main()
