"""Track pipeline fail streaks and optionally trigger fabricate proposals."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "memory" / "learning" / "fail_streak.json"


def _load() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"streak": 0, "last_error": None, "proposed": False}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"streak": 0, "last_error": None, "proposed": False}


def _save(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def record_outcome(success: bool, error: Optional[str] = None) -> Dict[str, Any]:
    state = _load()
    if success:
        state["streak"] = 0
        state["last_error"] = None
        state["proposed"] = False
    else:
        state["streak"] = int(state.get("streak") or 0) + 1
        state["last_error"] = (error or "")[:300]
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(state)
    return state


def maybe_propose_fabricate() -> Optional[Dict[str, Any]]:
    """If fail streak high and env enabled, return a fabricate tool_request."""
    if os.getenv("ETHER_AUTO_FABRICATE_ON_FAIL", "0") != "1":
        return None
    threshold = int(os.getenv("ETHER_FAIL_STREAK_THRESHOLD", "3"))
    state = _load()
    if int(state.get("streak") or 0) < threshold:
        return None
    if state.get("proposed"):
        return None
    err = (state.get("last_error") or "repeated failures").replace("\"", "'")[:120]
    name = f"fix_{state['streak']}_helper"
    state["proposed"] = True
    _save(state)
    return {
        "action": "fabricate",
        "name": name,
        "docstring": f"Helper proposed after fail streak: {err}",
        "purpose": f"Address repeated pipeline failure: {err}",
        "stub_only": os.getenv("ETHER_FABRICATE_STUB_ONLY", "0") == "1",
    }
