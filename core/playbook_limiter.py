"""Playbook / critique rate limiter.

Critical fix #2: stop playbook_coding_method_refresh spam.
Critical fix #7: one recovery per failure_type per window.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
STATE_PATH = ROOT / "artifacts" / "playbook_limiter.json"
WINDOW_S = int(os.getenv("ETHER_PLAYBOOK_WINDOW_S", "3600"))  # 1 hour


def _load() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"by_type": {}, "by_lesson": {}}


def _save(data: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def may_fire(key: str, *, kind: str = "type") -> bool:
    """Return True if we have not fired this key inside the window."""
    data = _load()
    bucket = data.setdefault("by_type" if kind == "type" else "by_lesson", {})
    now = time.time()
    last = float(bucket.get(key) or 0)
    if now - last < WINDOW_S:
        return False
    return True


def record_fire(key: str, *, kind: str = "type") -> None:
    data = _load()
    bucket = data.setdefault("by_type" if kind == "type" else "by_lesson", {})
    bucket[key] = time.time()
    # prune old
    cutoff = time.time() - WINDOW_S * 2
    for k in list(bucket.keys()):
        if float(bucket[k]) < cutoff:
            del bucket[k]
    _save(data)


def allow_playbook(failure_type: str, lesson_id: str) -> bool:
    ft = (failure_type or "unknown").strip().lower() or "unknown"
    lid = (lesson_id or "unknown").strip().lower() or "unknown"
    if not may_fire(ft, kind="type"):
        return False
    if not may_fire(lid, kind="lesson"):
        return False
    return True


def mark_playbook(failure_type: str, lesson_id: str) -> None:
    ft = (failure_type or "unknown").strip().lower() or "unknown"
    lid = (lesson_id or "unknown").strip().lower() or "unknown"
    record_fire(ft, kind="type")
    record_fire(lid, kind="lesson")
