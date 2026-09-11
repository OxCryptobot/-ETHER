"""ETHER desktop app.

The app owns functionality: Ollama, attach, Start/Stop LIVE.
The Control Matrix webpage is the dashboard (UX only).
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict

from scripts.live_host import consume, start_ollama

DASHBOARD = os.getenv("ETHER_DASHBOARD_URL", "https://etherbot.grok.me/?view=bus")


def boot() -> Dict[str, Any]:
    """Start local host. 4B if Ollama exists."""
    ollama = start_ollama()
    att = consume({"cmd": "attach"})
    att["booted"] = True
    att["ollama_started"] = ollama
    att["dashboard"] = DASHBOARD
    return att


def live_start() -> Dict[str, Any]:
    start_ollama()
    return consume({"cmd": "attach"})


def live_stop() -> Dict[str, Any]:
    return consume({"cmd": "stop"})


def status_line(payload: Dict[str, Any]) -> str:
    return f"lane={payload.get('live_lane')} ollama={payload.get('ollama')}"


def open_dashboard() -> str:
    """UX surface. Functionality stays in this process."""
    try:
        import webview  # type: ignore

        webview.create_window("ETHER", DASHBOARD)
        webview.start()
        return "webview"
    except Exception:
        import webbrowser

        webbrowser.open(DASHBOARD)
        return "browser_fallback"


def main() -> None:
    state = boot()
    kind = open_dashboard()
    state["shell"] = kind
    if kind == "browser_fallback":
        try:
            import tkinter as tk

            root = tk.Tk()
            root.title("ETHER")
            root.geometry("420x200")
            label = tk.StringVar(value=status_line(state))

            def refresh(payload: Dict[str, Any]) -> None:
                label.set(status_line(payload))

            tk.Label(root, text="ETHER app · Matrix is dashboard", font=("Segoe UI", 12)).pack(pady=10)
            tk.Label(root, textvariable=label).pack(pady=6)
            tk.Button(root, text="Start LIVE", width=20, command=lambda: refresh(live_start())).pack(pady=4)
            tk.Button(root, text="Stop LIVE", width=20, command=lambda: refresh(live_stop())).pack(pady=4)
            root.mainloop()
        except Exception:
            threading.Event().wait(1)


if __name__ == "__main__":
    main()
