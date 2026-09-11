"""Consume host_command. Standalone — no core/pydantic import."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def ollama_up() -> bool:
    url = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as res:
            return int(getattr(res, "status", 200) or 200) < 400
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def consume(command: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ollama = ollama_up()
    live_lane = "ollama_4b" if ollama else "grok_bus"
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "fast_lane": "matrix-worker",
        "live_lane": live_lane,
        "living_ok": True,
        "ollama": ollama,
        "grok_bus": not ollama,
        "cmd": (command or {}).get("cmd") or "attach",
        "consumed": True,
        "note": "live-host consumed command. 4B only if Ollama answered.",
    }
    root = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1])
    out = root / "artifacts" / "host_attach.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    payload["path"] = str(out)
    return payload


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "host_command.json"
    body = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"cmd": "attach"}
    print(json.dumps(consume(body), indent=2))
