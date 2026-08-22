"""Chat bridge — ETHER ↔ Grok over git-backed bus + immediate dashboard push.

2026-08-22e: escalate text promises immediate push via chat_sync, not 55s.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
CHAT = ROOT / "artifacts" / "chat"
OUTBOX = CHAT / "outbox"
INBOX = CHAT / "inbox"
PENDING = CHAT / "pending_grok.json"
DIRTY = CHAT / ".dirty"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mark_dirty() -> None:
    try:
        CHAT.mkdir(parents=True, exist_ok=True)
        DIRTY.write_text(_now(), encoding="utf-8")
    except Exception:
        pass


def clear_dirty() -> None:
    try:
        if DIRTY.exists():
            DIRTY.unlink()
    except Exception:
        pass


def is_dirty() -> bool:
    return DIRTY.exists()


def chat_paths_for_push() -> List[str]:
    paths: List[str] = []
    if not CHAT.exists():
        return paths
    for sub in ("inbox", "outbox", "archive", "turns"):
        d = CHAT / sub
        if d.exists():
            paths.append(f"artifacts/chat/{sub}")
    if (CHAT / "pending_grok.json").exists():
        paths.append("artifacts/chat/pending_grok.json")
    if (ROOT / "artifacts" / "chat_turn_latest.json").exists():
        paths.append("artifacts/chat_turn_latest.json")
    return paths


def set_pending_grok(envelope_id: str, text: str, turn_id: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        "updated": _now(),
        "status": "awaiting_grok",
        "envelope_id": envelope_id,
        "turn_id": turn_id,
        "text": (text or "")[:4000],
        "schema": "ether_pending_grok_v1",
    }
    CHAT.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    mark_dirty()
    return payload


def clear_pending_grok() -> None:
    try:
        if PENDING.exists():
            PENDING.unlink()
    except Exception:
        pass


def get_pending_grok() -> Optional[Dict[str, Any]]:
    if not PENDING.exists():
        return None
    try:
        return json.loads(PENDING.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_outbox(*, limit: int = 20) -> List[Dict[str, Any]]:
    from core.chat_bus import receive

    return receive(from_grok=False, limit=limit)


def list_inbox(*, limit: int = 20) -> List[Dict[str, Any]]:
    from core.chat_bus import receive

    return receive(from_grok=True, limit=limit)


def post_grok_reply(
    text: str,
    *,
    parent_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Dict[str, Any]:
    from core.chat_bus import envelope, send

    env = envelope(
        from_actor="grok",
        type_="agent_reply",
        payload={
            "text": (text or "")[:8000],
            "turn_id": turn_id,
            "channel": "grok",
            "source": "chat_bridge",
        },
        parent_id=parent_id,
        requires_reply=False,
    )
    path = send(env, to_grok=False)
    clear_pending_grok()
    mark_dirty()
    return {
        "ok": True,
        "envelope_id": env["id"],
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "updated": _now(),
    }


def escalate(
    text: str,
    *,
    job_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Dict[str, Any]:
    from core.chat_bus import envelope, send

    env = envelope(
        from_actor="ether_orchestrator",
        type_="operator",
        payload={
            "text": text,
            "routed": "escalate_grok",
            "turn_id": turn_id,
            "note": "Awaiting Grok — bus pushed immediately by dashboard",
        },
        job_id=job_id,
        requires_reply=True,
        parent_id=parent_id or turn_id,
    )
    path = send(env, to_grok=True)
    pending = set_pending_grok(env["id"], text, turn_id=turn_id)
    return {
        "tool": "escalate_grok",
        "ok": True,
        "envelope_id": env["id"],
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "pending": pending,
        "content": (
            "Queued for Grok. Dashboard pushes the bus immediately (async). "
            "Stay on channel Grok; reply appears when Grok writes inbox."
        ),
    }


def summary() -> Dict[str, Any]:
    from core.chat_bus import summary as bus_summary

    return {
        **bus_summary(),
        "dirty": is_dirty(),
        "pending_grok": get_pending_grok(),
        "bridge": True,
    }


if __name__ == "__main__":
    print(json.dumps(summary(), indent=2, default=str))
