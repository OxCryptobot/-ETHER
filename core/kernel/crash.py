"""Crash journal. Resume reads this instead of blind reset --hard."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

def _path(root: Path | None = None) -> Path:
    base = Path(root or os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[2])
    return base / "artifacts" / "crash_journal.jsonl"

def record(reason: str, **fields: Any) -> Dict[str, Any]:
    row = {"ts": datetime.now(timezone.utc).isoformat(), "reason": reason, "writer": "exe" if os.name == "nt" else "observe", **fields}
    if os.name != "nt":
        return row
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str)[:2000] + "\n")
    except OSError:
        pass
    return row

def last(root: Path | None = None) -> Dict[str, Any] | None:
    path = _path(root)
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        return json.loads(lines[-1]) if lines else None
    except Exception:
        return None
