"""Git-backed chat bus — ETHER ↔ Grok structured envelopes.

2026-08-22e: clear_session(fast=True) unlinks for instant Clear button.
2026-08-29: tick_once drains Control Matrix inbox -> outbox (git ack default).
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



PENDING_HOST = CHAT / "pending_host.json"
PENDING_HOST_SCHEMA = "ether_pending_host_v1"


def unanswered(inbox: List[Dict[str, Any]], outbox: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    parents = {str(e.get("parent_id") or "") for e in outbox if e.get("parent_id")}
    waiting: List[Dict[str, Any]] = []
    for env in inbox:
        if not env.get("requires_reply"):
            continue
        env_id = str(env.get("id") or "")
        if env_id and env_id not in parents:
            waiting.append(env)
    return waiting


def write_pending_host(envelope_id: str, text: str, status: str = "acked") -> Path:
    CHAT.mkdir(parents=True, exist_ok=True)
    body = {
        "updated": _now(),
        "status": status,
        "envelope_id": envelope_id,
        "text": (text or "")[:400],
        "schema": PENDING_HOST_SCHEMA,
    }
    PENDING_HOST.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return PENDING_HOST


def _ollama_reply(prompt: str) -> Optional[str]:
    if os.getenv("ETHER_CHAT_LLM", "0") != "1":
        return None
    try:
        import urllib.request

        body = json.dumps(
            {
                "model": os.getenv("ETHER_CHAT_MODEL", "qwen3.5:4b"),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are Host 4B on the ETHER git bus. Wheels ON. "
                            "Soft launch BLOCKED. Reply <=80 words. Do not claim living-agent."
                        ),
                    },
                    {"role": "user", "content": prompt[:1500]},
                ],
                "stream": False,
                "options": {"num_predict": 160},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434") + "/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        msg = (payload.get("message") or {}).get("content")
        text = str(msg or "").strip()
        return text[:800] or None
    except Exception:
        return None


def tick_once() -> Dict[str, Any]:
    """Drain one unanswered inbox envelope (Grok -> 4B) into outbox."""
    inbox = receive(from_grok=True, limit=48)
    outbox = receive(from_grok=False, limit=48)
    waiting = unanswered(inbox, outbox)
    if not waiting:
        return {"ok": True, "wrote": False, "reason": "caught up"}

    src = waiting[0]
    src_id = str(src.get("id") or "")
    src_text = str((src.get("payload") or {}).get("text") or "")
    job_id = src.get("job_id")
    llm = _ollama_reply(f"from={src.get('from')} type={src.get('type')}\n{src_text}")
    if llm:
        env = envelope(
            from_actor="ether",
            type_="agent_reply",
            payload={"text": llm},
            job_id=job_id,
            parent_id=src_id,
        )
    else:
        env = envelope(
            from_actor="git",
            type_="ack",
            payload={
                "text": (
                    f"Host tick parked parent {src_id}. 4B LLM skipped "
                    f"(ETHER_CHAT_LLM={os.getenv('ETHER_CHAT_LLM', '0')}). "
                    "FIFO still origin pending. Wheels ON."
                )
            },
            job_id=job_id,
            parent_id=src_id,
        )
    path = send(env, to_grok=True)
    write_pending_host(src_id, src_text, status="acked")
    return {
        "ok": True,
        "wrote": True,
        "id": env["id"],
        "from": env["from"],
        "parent_id": src_id,
        "path": str(path),
        "llm": bool(llm),
    }


if __name__ == "__main__":
    print(json.dumps(summary(), indent=2))
