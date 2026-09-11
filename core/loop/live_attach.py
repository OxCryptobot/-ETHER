"""LIVE attach. FAST is matrix-worker. LIVE is 4B if Ollama is up, else grok_bus."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from core.model_router import FAST_MODEL, grok_present, select_backend

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[2]).resolve()
OUT = ROOT / "artifacts" / "host_attach.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ollama_up() -> bool:
    url = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as res:
            return int(getattr(res, "status", 200) or 200) < 400
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def publish() -> Dict[str, Any]:
    ollama = ollama_up()
    grok = grok_present()
    live_lane = "ollama_4b" if ollama else ("grok_bus" if grok else "none")
    payload: Dict[str, Any] = {
        "updated": _now(),
        "ok": True,
        "fast_lane": "matrix-worker",
        "live_lane": live_lane,
        "ollama": ollama,
        "grok_bus": grok,
        "model": FAST_MODEL,
        "backend": select_backend("live"),
        "note": "FAST via GitHub ubuntu. LIVE via 4B when Ollama is up, else Dual-chat grok_bus.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
