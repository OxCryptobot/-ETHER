"""Batch 10 item 1: move files listed in attic/MANIFEST.json back to their original paths (git mv).

    python scripts/attic_restore.py core/phase3_idle.py   # one file
    python scripts/attic_restore.py --all                  # everything
    python scripts/attic_restore.py --list
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifest() -> list:
    return json.loads((ROOT / "attic" / "MANIFEST.json").read_text(encoding="utf-8"))["moved"]


def restore(paths: list) -> int:
    rows = {m["from"]: m for m in manifest()}
    n = 0
    for p in paths:
        m = rows.get(p)
        if m is None or not (ROOT / m["to"]).is_file():
            print(f"skip {p}: not in the attic")
            continue
        (ROOT / m["from"]).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", m["to"], m["from"]], cwd=str(ROOT), check=True)
        n += 1
    print(f"restored {n} file(s)")
    return n


def main(argv: list) -> int:
    if not argv or argv[0] == "--list":
        for m in manifest():
            print(m["from"])
        return 0
    restore([m["from"] for m in manifest()] if argv[0] == "--all" else argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
