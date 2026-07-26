#!/usr/bin/env python3
"""Safe git status snapshot."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, repo_root


def _run(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=str(repo_root()), capture_output=True, text=True)
    return (p.stdout or "").strip()


def main() -> None:
    emit(
        True,
        branch=_run("rev-parse", "--abbrev-ref", "HEAD"),
        porcelain=_run("status", "--porcelain"),
        dirty=bool(_run("status", "--porcelain")),
        head=_run("rev-parse", "--short", "HEAD"),
    )


if __name__ == "__main__":
    main()
