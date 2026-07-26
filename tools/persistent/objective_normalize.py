#!/usr/bin/env python3
"""Normalize a user objective string."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input


def main() -> None:
    inp = read_input()
    text = (inp.get("text") or inp.get("objective") or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text[:2000]
    emit(True, objective=text, chars=len(text))


if __name__ == "__main__":
    main()
