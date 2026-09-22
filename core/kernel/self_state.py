"""4B-readable self snapshot. Matrix may render; exe writes on NT."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

def snapshot(*, ollama: bool, pending_live: int, last: Dict[str, Any] | None) -> Dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "who": "exe" if os.name == "nt" else "observe",
        "ollama": bool(ollama),
        "pending_live": int(pending_live),
        "last_job": (last or {}).get("job_id"),
        "last_ok": (last or {}).get("ok"),
        "grok_required": False,
        "operator": "qwen3.5:4b" if ollama and os.name == "nt" else "waiting_1650",
    }

def write(root: Path, row: Dict[str, Any]) -> Path:
    path = Path(root) / "artifacts" / "self_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return path
