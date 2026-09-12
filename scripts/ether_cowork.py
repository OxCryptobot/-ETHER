"""Local Cowork board — tasks the desktop agent works."""
from __future__ import annotations

import os

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env:
        p = Path(env)
        if (p / "scripts").is_dir():
            return p.resolve()
    win = Path(r"C:\Users\Otcde\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]


ROOT = _root()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _board() -> Path:
    return _root() / "artifacts" / "cowork_board.json"


def load() -> List[Dict[str, Any]]:
    if not _board().is_file():
        return []
    try:
        data = json.loads(_board().read_text(encoding="utf-8"))
        return list(data.get("tasks") or [])
    except Exception:
        return []


def save(tasks: List[Dict[str, Any]]) -> None:
    _board().parent.mkdir(parents=True, exist_ok=True)
    _board().write_text(json.dumps({"updated": _now(), "tasks": tasks}, indent=2) + "\n", encoding="utf-8")


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
    out = _root() / "artifacts" / "cowork_out"
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:40] or "note"
    path = out / f"{safe}.md"
    path.write_text("# " + title + "\n\n" + body + "\n", encoding="utf-8")
    row = add("deliverable:" + title)
    return {"ok": True, "path": str(path.relative_to(ROOT)), "task": row}


def run_task(title: str) -> Dict[str, Any]:
    from scripts.ether_tools import search, list_tree
    files = search(title.split()[0] if title else "ether")[:8] or list_tree(8)
    notes = []
    for rel in files[:3]:
        p = _root() / rel
        try:
            notes.append(rel + "\n" + p.read_text(encoding="utf-8", errors="ignore")[:400])
        except Exception:
            continue
    body = "Task: " + title + "\n\n" + "\n\n".join(notes)
    out = deliver(title, body)
    close(out["task"]["id"])
    return {"ok": True, "files": files, "deliverable": out["path"]}





def schedule(title: str, every_min: int = 60) -> Dict[str, Any]:
    row = {"title": title, "every_min": int(every_min), "updated": _now()}
    (_root()/"artifacts"/"cowork_schedule.json").parent.mkdir(parents=True, exist_ok=True)
    (_root()/"artifacts"/"cowork_schedule.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row


def due() -> bool:
    if not (_root()/"artifacts"/"cowork_schedule.json").is_file():
        return False
    try:
        json.loads((_root()/"artifacts"/"cowork_schedule.json").read_text(encoding="utf-8"))
        return True
    except Exception:
        return False


def due_now() -> bool:
    p = _root() / "artifacts" / "cowork_schedule.json"
    if not p.is_file():
        return False
    try:
        row = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    every = int(row.get("every_min") or 60)
    last = str(row.get("last_run") or "")
    if not last:
        return True
    try:
        from datetime import datetime, timezone
        ts = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds() >= every * 60
    except Exception:
        return True


def mark_ran() -> None:
    p = _root() / "artifacts" / "cowork_schedule.json"
    if not p.is_file():
        return
    try:
        row = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return
    row["last_run"] = _now()
    p.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")


def set_folder(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_dir():
        return {"ok": False, "error": "not_dir"}
    marker = p / ".ether_folder"
    marker.write_text("cowork\n", encoding="utf-8")
    cfg = _root() / "artifacts" / "cowork_folder.json"
    cfg.write_text(json.dumps({"folder": str(p.resolve()), "ts": _now()}, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "folder": str(p.resolve())}
