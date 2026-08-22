"""Git-backed chat bus — ETHER ↔ Grok structured envelopes.

One hypothesis per message. Host and Grok both read/write the same
artifacts/chat/{inbox,outbox}/ paths. No external websocket required for
the host; Control Matrix and CLI surface the same files.

Doctrine:
- Training wheels stay ON.
- Labradorite still mandatory on non-infra FAIL.
- Chat never bypasses train_gates or live_budget.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
CHAT = ROOT / "artifacts" / "chat"
INBOX = CHAT / "inbox"
OUTBOX = CHAT / "outbox"
ARCHIVE = CHAT / "archive"

VALID_TYPES = {
    "critique_request",
    "critique_reply",
    "plan",
    "status",
    "recovery",
    "operator",
    "learn",
    "job_request",
    "ack",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    for d in (INBOX, OUTBOX, ARCHIVE):
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")


def envelope(
    *,
    from_actor: str,
    type_: str,
    payload: Dict[str, Any],
    job_id: Optional[str] = None,
    requires_reply: bool = False,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a typed chat envelope."""
    if type_ not in VALID_TYPES:
        raise ValueError(f"invalid chat type: {type_}")
    return {
        "id": f"chat_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        "ts": _now(),
        "from": from_actor,
        "type": type_,
        "payload": payload or {},
        "job_id": job_id,
        "requires_reply": bool(requires_reply),
        "parent_id": parent_id,
        "schema": "ether_chat_v1",
    }


def send(env: Dict[str, Any], *, to_grok: bool = True) -> Path:
    """Write envelope to outbox (ETHER→Grok) or inbox (operator/Grok→ETHER)."""
    _ensure_dirs()
    dest_dir = OUTBOX if to_grok else INBOX
    path = dest_dir / f"{env['id']}.json"
    path.write_text(json.dumps(env, indent=2), encoding="utf-8")
    return path


def receive(*, from_grok: bool = True, limit: int = 20) -> List[Dict[str, Any]]:
    """Read pending envelopes. from_grok=True → read inbox (Grok replies)."""
    _ensure_dirs()
    src = INBOX if from_grok else OUTBOX
    items: List[Dict[str, Any]] = []
    for p in sorted(src.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name == ".gitkeep":
            continue
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(items) >= limit:
            break
    return items


def archive(env_id: str) -> bool:
    """Move an envelope from inbox/outbox into archive."""
    _ensure_dirs()
    for folder in (INBOX, OUTBOX):
        src = folder / f"{env_id}.json"
        if src.exists():
            dst = ARCHIVE / src.name
            if dst.exists():
                dst = ARCHIVE / f"{src.stem}_{int(datetime.now().timestamp())}.json"
            src.rename(dst)
            return True
    return False


def post_operator(message: str, *, job_id: Optional[str] = None) -> Dict[str, Any]:
    """Operator → Grok quick message."""
    env = envelope(
        from_actor="operator",
        type_="operator",
        payload={"text": message},
        job_id=job_id,
        requires_reply=True,
    )
    send(env, to_grok=True)
    return env


def post_critique_request(
    job_id: str,
    failure_type: str,
    note: str,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """ETHER asks Grok / Labradorite for structured critique."""
    env = envelope(
        from_actor="ether",
        type_="critique_request",
        payload={
            "failure_type": failure_type,
            "note": note,
            "evidence": evidence or {},
        },
        job_id=job_id,
        requires_reply=True,
    )
    send(env, to_grok=True)
    return env


def summary() -> Dict[str, Any]:
    _ensure_dirs()
    return {
        "updated": _now(),
        "inbox_n": len([p for p in INBOX.glob("*.json") if p.name != ".gitkeep"]),
        "outbox_n": len([p for p in OUTBOX.glob("*.json") if p.name != ".gitkeep"]),
        "archive_n": len([p for p in ARCHIVE.glob("*.json") if p.name != ".gitkeep"]),
        "path": str(CHAT.relative_to(ROOT)).replace("\\", "/"),
    }


if __name__ == "__main__":
    print(json.dumps(summary(), indent=2))
