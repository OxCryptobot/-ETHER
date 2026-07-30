#!/usr/bin/env python3
"""Promote a quarantine tool after basic safety checks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, repo_root

RISKY = re.compile(
    r"\b(eval|exec|os\.system|os\.popen)\s*\(|shell\s*=\s*True"
    r"|subprocess\.(?:check_output|check_call)\s*\(|socket\.socket\s*\("
)


def main() -> None:
    inp = read_input()
    name = inp.get("filename") or inp.get("name")
    if not name:
        emit(False, error="filename required")
    src = repo_root() / "tools" / "quarantine" / name
    if not src.exists():
        emit(False, error=f"not found: {name}")
    code = src.read_text(encoding="utf-8")
    if RISKY.search(code):
        emit(False, error="risky patterns found; promotion refused (no override)")
    dst_dir = repo_root() / "tools" / "persistent"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    dst.write_text(code, encoding="utf-8")
    emit(True, promoted=str(dst.relative_to(repo_root())).replace("\\", "/"))


if __name__ == "__main__":
    main()
