"""Post-attach tick: drain LIVE on 1650, sleep short when FIFO has work."""
from __future__ import annotations
from typing import Any, Dict

def tick_after_attach() -> int:
    try:
        from scripts.drain_live_fifo import drain
        drain()
    except Exception:
        pass
    try:
        from core.kernel.poll import pending_count, poll_seconds
        return poll_seconds(pending_count())
    except Exception:
        return 60

def snapshot() -> Dict[str, Any]:
    try:
        from core.kernel.poll import pending_count, poll_seconds
        n = pending_count()
        return {"pending": n, "sleep": poll_seconds(n)}
    except Exception:
        return {"pending": 0, "sleep": 60}
