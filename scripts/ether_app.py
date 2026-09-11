"""In-house ETHER host app. No browser. Start/Stop LIVE on this machine."""
from __future__ import annotations

import json
from typing import Any, Dict

from scripts.live_host import consume


def live_start() -> Dict[str, Any]:
    return consume({"cmd": "attach"})


def live_stop() -> Dict[str, Any]:
    return consume({"cmd": "stop"})


def status_line(payload: Dict[str, Any]) -> str:
    lane = payload.get("live_lane")
    ollama = payload.get("ollama")
    return f"lane={lane} ollama={ollama}"


def main() -> None:
    import tkinter as tk

    root = tk.Tk()
    root.title("ETHER")
    root.geometry("420x220")
    label = tk.StringVar(value="in-house host · not a webpage")

    def refresh(payload: Dict[str, Any]) -> None:
        label.set(status_line(payload))

    tk.Label(root, text="ETHER", font=("Segoe UI", 18)).pack(pady=12)
    tk.Label(root, textvariable=label).pack(pady=8)
    tk.Button(root, text="Start LIVE", width=20, command=lambda: refresh(live_start())).pack(pady=4)
    tk.Button(root, text="Stop LIVE", width=20, command=lambda: refresh(live_stop())).pack(pady=4)
    refresh(live_start())
    root.mainloop()


if __name__ == "__main__":
    main()
