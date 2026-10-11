"""The source stays hidden until the model reads it."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def file_names(task: Dict[str, Any]) -> List[str]:
    names = [str(task["file"])]
    for name in task.get("also") or {}:
        if name not in names:
            names.append(str(name))
    return names


def blind_prompt(task: Dict[str, Any], failing: str) -> str:
    """Test failure and file names. Not the source."""
    lines = [
        "Failing cases:",
        failing or "the test failed",
        "Files:",
        *file_names(task),
        "Reply with exactly one line: READ: <one path above>",
    ]
    return "\n".join(lines)


def read_nudge(allowed: List[str], seen: List[str]) -> str:
    """Name the files still closed. Not the source, and not the patch."""
    closed = [name for name in allowed if name not in seen]
    opened = seen or ["none"]
    return (
        "Already open: " + ", ".join(opened) + "\n"
        "Still closed: " + ", ".join(closed) + "\n"
        "Reply with exactly one line: READ: <one still closed path>"
    )


def for_edit(prompt: str, task_prompt: str, names: Optional[List[str]] = None) -> str:
    """The edit turn must not still say READ. That line is only for the read turn."""
    kept = []
    for line in (prompt or "").splitlines():
        if line.startswith("Reply with exactly one line: READ:"):
            continue
        if line.startswith("Already open:") or line.startswith("Still closed:"):
            continue
        kept.append(line)
    extra = (task_prompt or "").strip()
    if names and len(names) > 1:
        need = " and ".join(f"def {name}" for name in names)
        extra = (extra + "\nReply with complete " + need + ".").strip()
    return "\n".join(kept).strip() + "\n\n" + extra + "\n"


def repair_ask(note: str, names: Optional[List[str]] = None) -> str:
    if names and len(names) > 1:
        need = " and ".join(f"def {name}" for name in names)
        tail = "Reply with complete " + need + "."
    else:
        tail = "Reply with a complete function only."
    return "Your last edit " + note + "\n" + tail + "\n"


def take_read(text: str, allowed: List[str]) -> Optional[str]:
    for line in (text or "").splitlines():
        if not line.startswith("READ:"):
            continue
        path = line.split(":", 1)[1].strip().strip("`").strip()
        if path in allowed:
            return path
    return None
