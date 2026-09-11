"""Consume host_command on a Windows runner. Fail-closed if no Ollama."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.loop.live_attach import publish


def consume(command: Dict[str, Any] | None = None) -> Dict[str, Any]:
    att = publish()
    cmd = (command or {}).get("cmd") or "attach"
    return {
        "ok": True,
        "cmd": cmd,
        "consumed": True,
        "ollama": bool(att.get("ollama")),
        "live_lane": att.get("live_lane"),
        "living_ok": bool(att.get("living_ok")),
        "note": "Runner consumed host_command. 4B only if Ollama answered.",
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "host_command.json"
    body = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"cmd": "attach"}
    print(json.dumps(consume(body), indent=2))
