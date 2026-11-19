"""One exe tick: liveness, LIVE drain, poll delay."""
from __future__ import annotations
from typing import Any, Dict
from core.kernel.poll import pending_count, poll_seconds
from core.kernel.writer import liveness

def tick() -> Dict[str, Any]:
    try:
        from scripts.drain_live_fifo import drain
        live = drain()
    except Exception as exc:
        live = {"ok": False, "error": type(exc).__name__}
    n = pending_count()
    snap = liveness(proc_alive=True, ollama_up=False, drain_alive=True)
    try:
        from scripts.live_host import ollama_up
        snap = liveness(proc_alive=True, ollama_up=bool(ollama_up()), drain_alive=True)
    except Exception:
        pass
    return {"liveness": snap, "pending": n, "sleep": poll_seconds(n), "live_drain": live, "kernel": "phase6"}
