"""The last tool result is the only memory the next prompt may see."""
from __future__ import annotations

import json
from pathlib import Path


def remember(root: Path, text: str) -> None:
    path = Path(root) / "artifacts" / "edit_memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"text": (text or "")[-400:]}) + "\n", encoding="utf-8")


def lesson_line(text: str, banned: str = "") -> str:
    """One failure the next edit may see. Never the banned patch."""
    text = " ".join((text or "").split())
    if not text or (banned and banned in text):
        return ""
    return text[-300:]


def recall(root: Path) -> str:
    path = Path(root) / "artifacts" / "edit_memory.json"
    if not path.is_file():
        return ""
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("text") or "")
    except Exception:
        return ""
