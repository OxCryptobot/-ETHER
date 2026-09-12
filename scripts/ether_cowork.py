"""Local Cowork board — tasks the desktop agent works."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "artifacts" / "cowork_board.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load() -> List[Dict[str, Any]]:
    if not BOARD.is_file():
        return []
    try:
        data = json.loads(BOARD.read_text(encoding="utf-8"))
        return list(data.get("tasks") or [])
    except Exception:
        return []


def save(tasks: List[Dict[str, Any]]) -> None:
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    BOARD.write_text(json.dumps({"updated": _now(), "tasks": tasks}, indent=2) + "\n", encoding="utf-8")


def add(title: str) -> Dict[str, Any]:
    tasks = load()
    row = {"id": f"t{len(tasks)+1}", "title": title, "status": "open", "ts": _now()}
    tasks.append(row)
    save(tasks)
    return row


def close(tid: str) -> bool:
    tasks = load()
    ok = False
    for t in tasks:
        if t.get("id") == tid:
            t["status"] = "done"
            ok = True
    save(tasks)
    return ok


def deliver(title: str, body: str) -> Dict[str, Any]:
    out = ROOT / "artifacts" / "cowork_out"
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:40] or "note"
    path = out / f"{safe}.md"
    path.write_text("# " + title + "\n\n" + body + "\n", encoding="utf-8")
    row = add("deliverable:" + title)
    return {"ok": True, "path": str(path.relative_to(ROOT)), "task": row}
