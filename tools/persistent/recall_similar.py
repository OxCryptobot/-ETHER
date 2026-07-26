#!/usr/bin/env python3
"""Recall similar success patterns by keyword overlap (no network)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, repo_root


def tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z_]{3,}", s.lower())}


def main() -> None:
    inp = read_input()
    query = inp.get("query") or inp.get("objective") or ""
    top_k = int(inp.get("top_k", 5))
    path = repo_root() / "memory" / "learning" / "success_patterns.jsonl"
    if not path.exists():
        emit(True, results=[], note="no patterns yet")
    q = tokens(query)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        score = len(q & tokens(row.get("objective", "") + " " + row.get("code", "")[:500]))
        rows.append({**row, "score": score})
    rows.sort(key=lambda r: r["score"], reverse=True)
    emit(True, results=rows[:top_k], count=len(rows))


if __name__ == "__main__":
    main()
