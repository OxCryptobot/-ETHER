"""ether:// protocol handler. Matrix Start/Stop LIVE land here on Windows."""
from __future__ import annotations

import sys
from typing import Dict

from scripts.live_host import consume


def parse_target(url: str) -> str:
    raw = (url or "ether://attach").split("://", 1)[-1]
    raw = raw.split("?", 1)[0].strip("/").lower()
    return "stop" if raw.startswith("stop") else "attach"


def handle(url: str) -> Dict[str, object]:
    cmd = parse_target(url)
    return consume({"cmd": cmd})


if __name__ == "__main__":
    print(handle(sys.argv[1] if len(sys.argv) > 1 else "ether://attach"))
