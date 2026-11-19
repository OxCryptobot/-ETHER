"""The last tool result is the only memory the next prompt may see."""
from __future__ import annotations

import json
from pathlib import Path


def remember(root: Path, text: str, slot: str = "text") -> None:
    path = Path(root) / "artifacts" / "edit_memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    data[slot] = (text or "")[-400:]
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")


def lesson_line(text: str, banned: str = "") -> str:
    """One failure the next edit may see. Never the banned patch, and never a case that already matched."""
    kept = []
    for part in (text or "").split(";"):
        piece = " ".join(part.split())
        if "returned " in piece and ", expected " in piece:
            got, _, want = piece.partition("returned ")[2].partition(", expected ")
            if got.strip() == want.strip():
                continue
        if piece:
            kept.append(piece)
    text = "; ".join(kept)
    if not text or (banned and banned in text):
        return ""
    return text[-300:]


def recall_task(root: Path, task_id: str) -> str:
    """The last failure of this task. Another task's failure is not shown."""
    path = Path(root) / "artifacts" / "edit_memory.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    lessons = data.get("lessons") if isinstance(data, dict) else None
    if not isinstance(lessons, dict):
        return ""
    return str(lessons.get(task_id) or "")


def remember_task(root: Path, task_id: str, text: str) -> None:
    path = Path(root) / "artifacts" / "edit_memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    lessons = data.get("lessons")
    if not isinstance(lessons, dict):
        lessons = {}
    lessons[task_id] = (text or "")[-400:]
    data["lessons"] = lessons
    data["text"] = lessons[task_id]
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")


def already_known(learned: str, note: str) -> bool:
    """True when this attempt fails the same way as the stored lesson."""
    return bool(learned and note and note in learned)


def recall(root: Path) -> str:
    path = Path(root) / "artifacts" / "edit_memory.json"
    if not path.is_file():
        return ""
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("text") or "")
    except Exception:
        return ""
