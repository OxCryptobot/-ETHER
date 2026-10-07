"""One process. Perceive, decide, edit, verify, remember. Git is not this process."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

Edit = Callable[[], Dict[str, Any]]


def _load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")


def cycle(
    root: Path,
    *,
    edit: Optional[Edit] = None,
    hands: bool = False,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    root = Path(root)
    art = root / "artifacts"
    stages = ["perceive"]
    from core.kernel.edit_memory import recall

    lesson = recall(root)
    stages.append("decide")
    if not hands:
        row = {
            "ok": True,
            "decision": "observe",
            "stages": stages + ["remember"],
            "honest": False,
            "lesson": lesson,
            "writers": [],
            "git": False,
        }
        _write(art / "agent.json", row)
        return row
    stages.append("act")
    if edit is None:
        from scripts.live_edit_tx import main as edit_main

        edit_main()
        edit_row = _load(art / "live_edit_tx.json")
    else:
        edit_row = dict(edit() or {})
        _write(art / "live_edit_tx.json", edit_row)
    stages.append("verify")
    from core.kernel.scale import advance

    scale = advance(root)
    stages.append("remember")
    from core.kernel.day_learn import learn

    learned = learn(root, now)
    held = edit_row.get("note") == "curriculum_hold"
    row = {
        "ok": True,
        "decision": "hold" if held else "edit",
        "stages": stages,
        "honest": bool(scale.get("honest")) if held else bool(edit_row.get("honest")),
        "lesson": lesson,
        "learned": bool(learned.get("skipped")),
        "scale": {"repeatable": scale.get("repeatable"), "checker_writes": (scale.get("checker") or {}).get("writes")},
        "writers": ["edit_tx"],
        "git": False,
    }
    _write(art / "agent.json", row)
    return row
