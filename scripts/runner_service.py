"""Register the GitHub runner as a service. Do not open a window. Do not start a second listener."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


def ensure_service() -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": True, "note": "observe_only"}
    from scripts.win_quiet import run_hidden

    query = run_hidden(["sc.exe", "query", "ETHER-1650"], timeout=15)
    text = (query.stdout or "") + (query.stderr or "")
    if "RUNNING" in text or "STOPPED" in text:
        return {"ok": True, "note": "service_present"}
    listener = Path(os.environ.get("ETHER_RUNNER_DIR") or r"C:\actions-runner") / "bin" / "Runner.Listener.exe"
    if not listener.is_file():
        return {"ok": False, "error": "no_listener"}
    running = run_hidden(["tasklist", "/FI", "IMAGENAME eq Runner.Listener.exe", "/NH"], timeout=10)
    if "runner.listener.exe" in (running.stdout or "").lower():
        return {"ok": True, "note": "listener_already_up"}
    created = run_hidden(
        ["sc.exe", "create", "ETHER-1650", "binPath=", f'"{listener} run"', "start=", "auto"],
        timeout=20,
    )
    if created.returncode != 0:
        return {"ok": False, "error": "create_failed", "rc": created.returncode}
    return {"ok": True, "note": "created"}
