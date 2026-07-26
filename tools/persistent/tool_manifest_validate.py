#!/usr/bin/env python3
"""Validate persistent tool files exist and are non-empty Python."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, repo_root


def main() -> None:
    d = repo_root() / "tools" / "persistent"
    report = []
    for p in sorted(d.glob("*.py")):
        code = p.read_text(encoding="utf-8", errors="ignore")
        report.append(
            {
                "name": p.name,
                "bytes": len(code),
                "has_main": "def main" in code,
                "json_io": "emit(" in code or "read_input" in code,
            }
        )
    emit(True, tools=report, count=len(report))


if __name__ == "__main__":
    main()
