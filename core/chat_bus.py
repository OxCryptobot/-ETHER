"""Git-backed chat bus — ETHER ↔ Grok structured envelopes.

2026-08-22e: clear_session(fast=True) unlinks for instant Clear button.
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
    "agent_turn",
    "agent_reply",
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
    _ensure_dirs()
    dest_dir = OUTBOX if to_grok else INBOX
    path = dest_dir / f"{env['id']}.json"
    path.write_text(json.dumps(env, indent=2), encoding="utf-8")
    return path


def receive(*, from_grok: bool = True, limit: int = 20) -> List[Dict[str, Any]]:
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


def _wipe_folder(folder: Path) -> int:
    """Unlink envelopes (fast clear). Keeps .gitkeep."""
    n = 0
    if not folder.exists():
        return 0
    for p in list(folder.glob("*.json")):
        if p.name == ".gitkeep":
            continue
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    return n


def _archive_folder(folder: Path) -> int:
    n = 0
    if not folder.exists():
        return 0
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    for p in list(folder.glob("*.json")):
        if p.name == ".gitkeep":
            continue
        dst = ARCHIVE / p.name
        if dst.exists():
            dst = ARCHIVE / f"{p.stem}_clr_{stamp}.json"
        try:
            p.rename(dst)
            n += 1
        except OSError:
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
    return n


def clear_session(*, keep_archive: bool = True, fast: bool = True) -> Dict[str, Any]:
    """Clear Chat. fast=True (default): unlink inbox/outbox for instant UI.

    keep_archive only matters when fast=False (rename into archive/).
    """
    _ensure_dirs()
    if fast:
        wiped_in = _wipe_folder(INBOX)
        wiped_out = _wipe_folder(OUTBOX)
        return {
            "ok": True,
            "fast": True,
            "wiped_inbox": wiped_in,
            "wiped_outbox": wiped_out,
            "archived_inbox": 0,
            "archived_outbox": 0,
            "updated": _now(),
        }
    archived_in = _archive_folder(INBOX)
    archived_out = _archive_folder(OUTBOX)
    wiped_archive = 0
    if not keep_archive:
        wiped_archive = _wipe_folder(ARCHIVE)
    return {
        "ok": True,
        "fast": False,
        "archived_inbox": archived_in,
        "archived_outbox": archived_out,
        "wiped_archive": wiped_archive,
        "updated": _now(),
    }


def post_operator(message: str, *, job_id: Optional[str] = None) -> Dict[str, Any]:
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
    turns_n = 0
    turns_dir = CHAT / "turns"
    if turns_dir.exists():
        turns_n = len([p for p in turns_dir.glob("turn_*.json")])
    return {
        "updated": _now(),
        "inbox_n": len([p for p in INBOX.glob("*.json") if p.name != ".gitkeep"]),
        "outbox_n": len([p for p in OUTBOX.glob("*.json") if p.name != ".gitkeep"]),
        "archive_n": len([p for p in ARCHIVE.glob("*.json") if p.name != ".gitkeep"]),
        "turns_n": turns_n,
        "path": str(CHAT.relative_to(ROOT)).replace("\\", "/"),
        "orchestrator": True,
    }


if __name__ == "__main__":
    print(json.dumps(summary(), indent=2))
