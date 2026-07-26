#!/usr/bin/env python3
"""Strip markdown code fences from LLM output."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input


def main() -> None:
    inp = read_input()
    text = (inp.get("text") or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    emit(True, text=text)


if __name__ == "__main__":
    main()
