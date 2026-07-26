#!/usr/bin/env python3
"""Build a few-shot prompt block from success patterns."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, repo_root


def tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z_]{3,}", (s or "").lower()))


def main() -> None:
    inp = read_input()
    query = inp.get("query") or ""
    k = int(inp.get("top_k", 3))
    path = repo_root() / "memory" / "learning" / "success_patterns.jsonl"
    if not path.exists():
        emit(True, block="", note="no patterns")
    q = tokens(query)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        score = len(q & tokens(row.get("objective", "")))
        rows.append((score, row))
    rows.sort(key=lambda x: x[0], reverse=True)
    parts = []
    for score, row in rows[:k]:
        parts.append(f"# example objective: {row.get('objective','')}\n{row.get('code','')}\n")
    emit(True, block="\n".join(parts), used=len(parts))


if __name__ == "__main__":
    main()
