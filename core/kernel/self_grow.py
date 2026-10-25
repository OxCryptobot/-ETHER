"""The system picks its own next failure. No planted hello-world after the toy is proven."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

QUEUE: List[Dict[str, str]] = [
    {"id": "merge_sorted", "fixture": "fixtures/repo_oracle_merge", "file": "merge.py"},
    {"id": "ledger", "fixture": "fixtures/repo_oracle_ledger", "file": "ledger.py"},
    {"id": "wallet", "fixture": "fixtures/repo_oracle_wallet", "file": "wallet.py"},
]


def _path(root: Path) -> Path:
    return Path(root) / "artifacts" / "growth.json"


def load(root: Path) -> Dict[str, Any]:
    path = _path(root)
    if not path.is_file():
        return {"done": [], "current": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"done": [], "current": None}
    data.setdefault("done", [])
    return data if isinstance(data, dict) else {"done": [], "current": None}


def save(root: Path, data: Dict[str, Any]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def next_real(root: Path) -> Optional[Dict[str, str]]:
    """The first real task not marked done in the published file. A missing file means start at the first."""
    done = set(str(item) for item in (load(root).get("done") or []))
    for item in QUEUE:
        if item["id"] not in done:
            return item
    return QUEUE[0] if QUEUE else None


def mark_done(root: Path, task_id: str) -> None:
    data = load(root)
    done = [str(item) for item in (data.get("done") or [])]
    if task_id not in done:
        done.append(task_id)
    data["done"] = done
    data["current"] = task_id
    data["ts"] = datetime.now(timezone.utc).isoformat()
    save(root, data)


def greeter_proven(root: Path) -> bool:
    """The toy has passed. Stop replaying it."""
    path = Path(root) / "artifacts" / "repo_fail.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return len(data.get("passes") or []) >= 2
