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


def take_read(text: str, allowed: List[str]) -> Optional[str]:
    for line in (text or "").splitlines():
        if not line.startswith("READ:"):
            continue
        path = line.split(":", 1)[1].strip().strip("`").strip()
        if path in allowed:
            return path
    return None
