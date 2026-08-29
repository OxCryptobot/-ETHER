"""ether_chat_v1 git bus — Grok/operator write inbox; 4B/git write outbox.

The Control Matrix cannot exec on Windows. This module is the host-side drain:
read unanswered inbox, write one outbox envelope, optionally commit.

LLM calls are opt-in (ETHER_CHAT_LLM=1). Default tick is a git ack so Dual chat
moves even when Ollama is down. Style after green (pep8-python-reviewer).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = "ether_chat_v1"
PENDING_HOST_SCHEMA = "ether_pending_host_v1"
INBOX_REL = Path("artifacts") / "chat" / "inbox"
OUTBOX_REL = Path("artifacts") / "chat" / "outbox"
PENDING_HOST_REL = Path("artifacts") / "chat" / "pending_host.json"

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp(prefix: str = "chat") -> str:
    d = datetime.now(timezone.utc)
    rand = uuid.uuid4().hex[:6]
    return f"{prefix}_{d.strftime('%Y%m%d_%H%M%S')}_{rand}"


def inbox_dir(root: Optional[Path] = None) -> Path:
    return (root or ROOT) / INBOX_REL


def outbox_dir(root: Optional[Path] = None) -> Path:
    return (root or ROOT) / OUTBOX_REL


def pending_host_path(root: Optional[Path] = None) -> Path:
    return (root or ROOT) / PENDING_HOST_REL


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def load_envelopes(folder: Path, limit: int = 48) -> List[Dict[str, Any]]:
    if not folder.is_dir():
        return []
    files = sorted(
        [p for p in folder.glob("*.json") if p.name != ".gitkeep"],
        key=lambda p: p.name,
        reverse=True,
    )[:limit]
    out: List[Dict[str, Any]] = []
    for path in files:
        row = _read_json(path)
        if row and isinstance(row.get("id"), str):
            out.append(row)
    out.sort(key=lambda e: str(e.get("ts") or ""))
    return out


def make_envelope(
    *,
    from_actor: str,
    type_: str,
    text: str,
    job_id: str = "",
    parent_id: str = "",
    requires_reply: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"text": text}
    if extra:
        payload.update(extra)
    return {
        "id": _stamp("chat"),
        "ts": _now(),
        "from": from_actor,
        "type": type_,
        "payload": payload,
        "job_id": job_id,
        "requires_reply": bool(requires_reply),
        "parent_id": parent_id,
        "schema": SCHEMA,
    }


def write_envelope(folder: Path, env: Dict[str, Any]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{env['id']}.json"
    path.write_text(json.dumps(env, indent=2) + "\n", encoding="utf-8")
    return path


def unanswered_inbox(inbox: Iterable[Dict[str, Any]], outbox: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    parents = {str(e.get("parent_id") or "") for e in outbox if e.get("parent_id")}
    waiting: List[Dict[str, Any]] = []
    for env in inbox:
        if not env.get("requires_reply"):
            continue
        env_id = str(env.get("id") or "")
        if env_id and env_id not in parents:
            waiting.append(env)
    return waiting


def write_pending_host(root: Path, envelope_id: str, text: str, status: str = "acked") -> Path:
    path = pending_host_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "updated": _now(),
        "status": status,
        "envelope_id": envelope_id,
        "text": text[:400],
        "schema": PENDING_HOST_SCHEMA,
    }
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


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


def tick_once(root: Optional[Path] = None) -> Dict[str, Any]:
    """Drain at most one unanswered inbox envelope into outbox."""
    base = root or ROOT
    inbox = load_envelopes(inbox_dir(base))
    outbox = load_envelopes(outbox_dir(base))
    waiting = unanswered_inbox(inbox, outbox)
    if not waiting:
        return {"ok": True, "wrote": False, "reason": "caught up"}

    src = waiting[0]
    src_id = str(src.get("id") or "")
    src_text = str((src.get("payload") or {}).get("text") or "")
    job_id = str(src.get("job_id") or "")
    llm = _ollama_reply(f"from={src.get('from')} type={src.get('type')}\n{src_text}")
    if llm:
        env = make_envelope(
            from_actor="ether",
            type_="agent_reply",
            text=llm,
            job_id=job_id,
            parent_id=src_id,
        )
    else:
        env = make_envelope(
            from_actor="git",
            type_="ack",
            text=(
                f"Host tick parked parent {src_id}. 4B LLM skipped "
                f"(ETHER_CHAT_LLM={os.getenv('ETHER_CHAT_LLM', '0')}). "
                "FIFO still origin pending. Wheels ON."
            ),
            job_id=job_id,
            parent_id=src_id,
        )
    path = write_envelope(outbox_dir(base), env)
    write_pending_host(base, src_id, src_text, status="acked")
    return {
        "ok": True,
        "wrote": True,
        "id": env["id"],
        "from": env["from"],
        "parent_id": src_id,
        "path": str(path),
        "llm": bool(llm),
    }
