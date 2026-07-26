#!/usr/bin/env python3
"""Summarize git diff --stat."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, repo_root


def main() -> None:
    p = subprocess.run(
        ["git", "diff", "--stat"],
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
    )
    emit(p.returncode == 0, stat=(p.stdout or "").strip(), stderr=(p.stderr or "")[:500])


if __name__ == "__main__":
    main()
