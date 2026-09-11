"""Persistent local consumer. No operator PowerShell after first install."""
from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.live_host import consume

ROOT = Path(__file__).resolve().parents[1]
CMD = ROOT / "artifacts" / "host_command.json"


def tick() -> dict:
    body = {"cmd": "attach"}
    if CMD.is_file():
        try:
            body = json.loads(CMD.read_text(encoding="utf-8"))
        except Exception:
            pass
    return consume(body)


def main() -> None:
    while True:
        tick()
        time.sleep(60)


if __name__ == "__main__":
    print(json.dumps(tick()))
