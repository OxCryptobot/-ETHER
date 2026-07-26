"""In-progress run file for live dashboard coding view."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "memory" / "runs" / "in_progress.json"


def write_progress(task_id: str, objective: str, stage: str, detail: str = "", **extra: Any) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "task_id": task_id,
        "objective": objective[:200],
        "stage": stage,
        "detail": detail[:200],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def clear_progress() -> None:
    if PATH.exists():
        try:
            PATH.unlink()
        except Exception:
            pass


def read_progress() -> Optional[Dict[str, Any]]:
    if not PATH.exists():
        return None
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
