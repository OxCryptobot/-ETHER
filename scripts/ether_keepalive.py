"""Persistent local consumer. Matrix Start/Stop LIVE via host_command."""
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
    out = consume(body)
    out["halt"] = str(body.get("cmd") or "") == "stop"
    return out


def main() -> None:
    while True:
        out = tick()
        if out.get("halt"):
            break
        time.sleep(60)


if __name__ == "__main__":
    print(json.dumps(tick()))
