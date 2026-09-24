"""Ubuntu / Grok / Matrix must not write attach truth."""
from __future__ import annotations
from typing import Any, Dict
from core.kernel.writer import allow_attach_write, ATTACH_WRITER

def attach_payload(*, ollama_up: bool, prev: Dict[str, Any], cmd: str, extra: Dict[str, Any] | None = None) -> tuple[bool, Dict[str, Any]]:
    if not allow_attach_write(ollama_up=ollama_up, writer_claim=ATTACH_WRITER):
        row = dict(prev)
        row["cmd"] = cmd or row.get("cmd") or "attach"
        row["consumed"] = True
        row["clobber"] = False
        row["note"] = "observe only. exe owns attach."
        row.setdefault("live_lane", "grok_bus")
        row.setdefault("writer", ATTACH_WRITER)
        return False, row
    payload: Dict[str, Any] = {
        "ok": True,
        "live_lane": "ollama_4b" if ollama_up else "grok_bus",
        "ollama": bool(ollama_up),
        "grok_bus": not ollama_up,
        "cmd": cmd or "attach",
        "consumed": True,
        "clobber": False,
        "writer": ATTACH_WRITER,
        "note": "exe attach",
    }
    if extra:
        payload.update(extra)
    return True, payload
