"""Reads a kept result. Cannot write. That is the checker."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def check(root: Path, goal: str) -> Dict[str, Any]:
    """Confirm a kept goal is in the file and in the list. Read only."""
    path = Path(root) / "artifacts" / "sota.json"
    if not path.is_file():
        return {"ok": False, "gem": "checker", "reason": "no state"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "gem": "checker", "reason": "bad state"}
    goals = [str(item) for item in (data.get("goals") or [])]
    if goal not in goals:
        return {"ok": False, "gem": "checker", "reason": "not kept", "goal": goal}
    last = data.get("last") if isinstance(data.get("last"), dict) else {}
    file = str(last.get("file") or "")
    present = False
    if file and (Path(root) / file).is_file():
        present = f"def {goal.split('_', 1)[-1]}" in (Path(root) / file).read_text(encoding="utf-8", errors="ignore")
    return {"ok": True, "gem": "checker", "goal": goal, "file": file, "in_file": present, "writes": False}
