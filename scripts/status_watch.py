#!/usr/bin/env python3
"""Simple local status watcher for @ETHER.

Usage:
    python scripts/status_watch.py

It prints the current STATUS.md and can optionally poll GitHub.
"""

from __future__ import annotations

import time
from pathlib import Path

STATUS_FILE = Path(__file__).parent.parent / "STATUS.md"


def main() -> None:
    print("@ETHER Status Watcher")
    print("=" * 50)

    if not STATUS_FILE.exists():
        print("STATUS.md not found.")
        return

    content = STATUS_FILE.read_text(encoding="utf-8")
    print(content)
    print("=" * 50)
    print("Tip: re-run this script or refresh STATUS.md on GitHub to see updates.")


if __name__ == "__main__":
    main()
