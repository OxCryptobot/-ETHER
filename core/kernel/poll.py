"""Poll cadence. Pending work sleeps short. Idle sleeps long."""
from __future__ import annotations
from pathlib import Path
from core.kernel.queue import queue_root

BUSY_SEC = 12
IDLE_SEC = 60

def pending_count(pending: Path | None = None) -> int:
    d = Path(pending) if pending is not None else queue_root()
    if not d.is_dir():
        return 0
    return len([p for p in d.glob("*.json") if p.name != ".gitkeep"])

def poll_seconds(n: int | None = None) -> int:
    count = pending_count() if n is None else int(n)
    return BUSY_SEC if count > 0 else IDLE_SEC
