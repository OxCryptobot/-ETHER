"""Path helpers."""

from __future__ import annotations

from pathlib import Path


def as_posix_str(path: str | Path) -> str:
    return Path(path).as_posix()
