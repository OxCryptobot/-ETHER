#!/usr/bin/env python3
"""List tools in quarantine."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, repo_root


def main() -> None:
    d = repo_root() / "tools" / "quarantine"
    files = sorted(p.name for p in d.glob("*.py")) if d.exists() else []
    emit(True, tools=files, count=len(files))


if __name__ == "__main__":
    main()
