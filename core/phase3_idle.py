"""Idle hook for ether_host — Phase 3 tick + progress publish.

Called when pending is empty. Never enqueues greeter. Never lifts wheels.
"""
from __future__ import annotations

from typing import Any, Dict


def idle_tick() -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": True, "soft_launch": False}
    try:
        from core.phase3_evolve import tick

        ev = tick(enqueue=False, force_critique=False)
        out["evolve"] = {
            "unlocked": ev.get("unlocked"),
            "ok": ev.get("ok"),
            "thread_id": ev.get("thread_id"),
        }
    except Exception as exc:
        out["evolve_error"] = f"{type(exc).__name__}: {exc}"[:160]
        out["ok"] = False
    try:
        from core.build_progress import compute

        prog = compute()
        out["progress_pct"] = prog.get("overall_pct")
        out["progress_bar"] = prog.get("overall_bar")
    except Exception as exc:
        out["progress_error"] = f"{type(exc).__name__}: {exc}"[:160]
        out["ok"] = False
    return out
