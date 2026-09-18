"""Attach / liveness ownership. Only the Windows exe writes truth."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any, Dict

ATTACH_WRITER = "exe"


def allow_attach_write(*, ollama_up: bool, writer_claim: str | None = None) -> bool:
    if os.name == "nt":
        return True
    if writer_claim == ATTACH_WRITER:
        return False
    if ollama_up:
        return False
    return False


def liveness(*, proc_alive: bool, ollama_up: bool, drain_alive: bool) -> Dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "proc": bool(proc_alive),
        "ollama": bool(ollama_up),
        "drain": bool(drain_alive),
        "writer": ATTACH_WRITER if os.name == "nt" else "observe",
        "ok": bool(proc_alive),
    }
