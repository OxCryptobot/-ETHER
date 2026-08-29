"""FAST: git-bus drain writes outbox without Ollama."""

from __future__ import annotations

import json
from pathlib import Path

from core.chat_bus import (
    load_envelopes,
    make_envelope,
    tick_once,
    unanswered_inbox,
    write_envelope,
    write_pending_host,
)


def _seed_inbox(root: Path, *, requires_reply: bool = True) -> dict:
    env = make_envelope(
        from_actor="operator",
        type_="operator",
        text="Status of host and Wave A.",
        job_id="p3_31_skip_llm",
        requires_reply=requires_reply,
    )
    write_envelope(root / "artifacts" / "chat" / "inbox", env)
    return env


def test_unanswered_filters_replied(tmp_path: Path) -> None:
    inbox_env = make_envelope(from_actor="operator", type_="operator", text="hi", requires_reply=True)
    reply = make_envelope(
        from_actor="git",
        type_="ack",
        text="parked",
        parent_id=str(inbox_env["id"]),
    )
    waiting = unanswered_inbox([inbox_env], [reply])
    assert waiting == []


def test_tick_once_writes_git_ack(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ETHER_CHAT_LLM", raising=False)
    src = _seed_inbox(tmp_path)
    result = tick_once(tmp_path)
    assert result["ok"] is True
    assert result["wrote"] is True
    assert result["from"] == "git"
    assert result["parent_id"] == src["id"]
    outbox = load_envelopes(tmp_path / "artifacts" / "chat" / "outbox")
    assert len(outbox) == 1
    assert outbox[0]["parent_id"] == src["id"]
    pending = json.loads((tmp_path / "artifacts" / "chat" / "pending_host.json").read_text(encoding="utf-8"))
    assert pending["envelope_id"] == src["id"]
    assert pending["status"] == "acked"


def test_tick_once_caught_up(tmp_path: Path) -> None:
    _seed_inbox(tmp_path, requires_reply=False)
    result = tick_once(tmp_path)
    assert result["ok"] is True
    assert result["wrote"] is False
    assert result["reason"] == "caught up"


def test_write_pending_host_schema(tmp_path: Path) -> None:
    path = write_pending_host(tmp_path, "chat_1", "hello", status="queued")
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["schema"] == "ether_pending_host_v1"
    assert body["envelope_id"] == "chat_1"
