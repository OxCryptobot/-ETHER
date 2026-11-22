"""Medic stands down while the host heartbeat is fresh.

Do not enqueue medic_hb / playbook refresh when phase=idle and beat age ≤ STALE_SEC.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

STALE_SEC = 8 * 60


def heartbeat_age_sec(heartbeat: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    if not heartbeat:
        return None
    try:
        ts = datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds()


def medic_stand_down(status: Dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    """True = do not farm. Idle/running with a fresh beat is healthy."""
    phase = str(status.get("phase") or "").lower()
    if phase not in ("idle", "running", "ok"):
        return False
    age = heartbeat_age_sec(status.get("heartbeat"), now=now)
    if age is None:
        return False
    return age <= STALE_SEC
