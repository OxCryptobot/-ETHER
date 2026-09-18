"""Typed kernel events. Matrix may render these; only exe appends them."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

KINDS = frozenset({"JobStarted", "ToolDone", "TestsFailed", "TestsPassed", "Aborted", "Attach", "Critique", "Crash"})

class Event(dict):
    pass

def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]

def emit(kind: str, **fields: Any) -> Optional[Dict[str, Any]]:
    if kind not in KINDS:
        kind = "Aborted"
        fields.setdefault("reason", "unknown_event")
    row: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "writer": "exe" if os.name == "nt" else "observe",
        **fields,
    }
    if os.name != "nt" and kind in {"Attach", "Crash"} and fields.get("force") is not True:
        return row
    path = _root() / "artifacts" / "kernel_events.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str)[:2000] + "\n")
    except OSError:
        return row
    return row
