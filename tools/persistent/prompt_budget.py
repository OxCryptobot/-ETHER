#!/usr/bin/env python3
"""Estimate prompt size and optionally truncate."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input


def main() -> None:
    inp = read_input()
    text = inp.get("text") or ""
    max_chars = int(inp.get("max_chars", 8000))
    truncated = text[:max_chars]
    emit(
        True,
        chars=len(text),
        approx_tokens=len(text) // 4,
        truncated=len(text) > max_chars,
        text=truncated if inp.get("truncate") else None,
    )


if __name__ == "__main__":
    main()
