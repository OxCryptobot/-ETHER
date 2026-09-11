"""ETHER desktop app. Host only. No popup windows by default."""
from __future__ import annotations

import os
from typing import Any, Dict

from scripts.live_host import consume, ollama_up, start_ollama

DASHBOARD = os.getenv("ETHER_DASHBOARD_URL", "https://etherbot.grok.me/?view=bus")


def boot() -> Dict[str, Any]:
    ollama = start_ollama()
    att = consume({"cmd": "attach"})
    att["booted"] = True
    att["ollama_started"] = ollama
    att["dashboard"] = DASHBOARD
    att["health"] = health()
    return att


def live_start() -> Dict[str, Any]:
    start_ollama()
    return consume({"cmd": "attach"})


def live_stop() -> Dict[str, Any]:
    return consume({"cmd": "stop"})


def health() -> Dict[str, Any]:
    return {"ollama": ollama_up(), "dashboard": DASHBOARD, "ok": True}


def status_line(payload: Dict[str, Any]) -> str:
    return f"lane={payload.get('live_lane')} ollama={payload.get('ollama')}"


def shell_kind() -> str:
    return "headless"


def open_dashboard() -> str:
    """Dashboard is the existing Matrix tab. This app does not spawn windows."""
    return "headless"


def run_e2e() -> Dict[str, Any]:
    started = boot()
    stopped = live_stop()
    restarted = live_start()
    return {
        "ok": bool(started.get("booted") and restarted.get("consumed")),
        "boot": started,
        "stop": stopped,
        "start": restarted,
        "health": health(),
        "shell": shell_kind(),
        "dashboard": DASHBOARD,
    }


def main() -> None:
    state = boot()
    print(status_line(state))
    print("dashboard", DASHBOARD)
    print("no popup. Matrix tab is the UX.")


if __name__ == "__main__":
    main()
