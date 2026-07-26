#!/usr/bin/env python3
"""Flag risky execution patterns in source."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, safe_path

RULES = [
    ("eval", re.compile(r"\beval\s*\(")),
    ("exec", re.compile(r"\bexec\s*\(")),
    ("os_system", re.compile(r"os\.system\s*\(")),
    ("shell_true", re.compile(r"shell\s*=\s*True")),
    ("pickle_load", re.compile(r"pickle\.loads?\s*\(")),
]


def main() -> None:
    inp = read_input()
    text = inp.get("text")
    if not text and inp.get("path"):
        text = safe_path(inp["path"]).read_text(encoding="utf-8", errors="ignore")
    if text is None:
        emit(False, error="text or path required")
    hits = [{"rule": n, "count": len(rx.findall(text))} for n, rx in RULES if rx.search(text)]
    emit(True, findings=hits, risky=bool(hits))


if __name__ == "__main__":
    main()
