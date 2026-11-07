"""One snapshot of the machine. Published each tick. Read only."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def snapshot(root: Path) -> Dict[str, Any]:
    """What the machine is doing right now. No side effects."""
    root = Path(root)
    art = root / "artifacts"
    row: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "os": os.name,
        "root": str(root),
    }
    try:
        usage = shutil.disk_usage(root)
        row["disk_free_gb"] = round(usage.free / (1024 ** 3), 1)
        row["disk_total_gb"] = round(usage.total / (1024 ** 3), 1)
    except Exception:
        row["disk_free_gb"] = None
    alive = _read(art / "app_alive.json")
    row["ollama"] = bool(alive.get("ollama"))
    row["alive_ts"] = str(alive.get("ts") or "")
    sota = _read(art / "sota.json")
    goals = sota.get("goals") if isinstance(sota.get("goals"), list) else []
    last = sota.get("last") if isinstance(sota.get("last"), dict) else {}
    row["kept"] = len(goals)
    row["last_goal"] = str(last.get("goal") or "")
    row["last_kept"] = bool(last.get("kept"))
    row["batch_size"] = int(sota.get("kept_n") or 0)
    return row


def write(root: Path) -> Dict[str, Any]:
    row = snapshot(root)
    path = Path(root) / "artifacts" / "env.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row


def _read(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
