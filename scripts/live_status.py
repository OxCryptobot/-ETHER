"""Honest LIVE status. Ubuntu may write this. Never host_attach.
Stale if app_alive is not today or older than 6h. An open window is not LIVE.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
MAX_AGE_H = 6.0


def _parse(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def judge(ts: str, ollama: bool, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    dt = _parse(ts)
    age = None if dt is None else (now - dt).total_seconds() / 3600.0
    same_day = bool(dt and dt.date() == now.date())
    stale = age is None or age > MAX_AGE_H or not same_day
    return {
        "live": (not stale) and bool(ollama),
        "stale": stale,
        "age_hours": None if age is None else round(age, 2),
        "max_age_hours": MAX_AGE_H,
        "same_utc_day": same_day,
    }


def write() -> Dict[str, Any]:
    alive: Dict[str, Any] = {}
    attach: Dict[str, Any] = {}
    p = ROOT / "artifacts" / "app_alive.json"
    if p.is_file():
        try:
            alive = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            alive = {}
    q = ROOT / "artifacts" / "host_attach.json"
    if q.is_file():
        try:
            attach = json.loads(q.read_text(encoding="utf-8"))
        except Exception:
            attach = {}
    ts = str(alive.get("ts") or "")
    row = judge(ts, bool(attach.get("ollama")))
    row.update({
        "require": "scripts.host_main.tick on 1650",
        "github_runner": "optional",
        "app_alive_ts": ts,
        "attach_updated": attach.get("updated"),
        "attach_ollama": attach.get("ollama"),
        "writer": attach.get("writer"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "note": "open exe is not LIVE. stale app_alive is FAIL.",
    })
    out = ROOT / "artifacts" / "live_status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row


if __name__ == "__main__":
    print(json.dumps(write(), indent=2))
