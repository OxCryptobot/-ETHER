"""Cap exploding jsonl traces (WinError 206 class)."""
from __future__ import annotations
from pathlib import Path

def trim_jsonl(path: Path, *, max_lines: int = 400) -> int:
    p = Path(path)
    if not p.is_file():
        return 0
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= max_lines:
        return 0
    keep = lines[-max_lines:]
    p.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return len(lines) - len(keep)
