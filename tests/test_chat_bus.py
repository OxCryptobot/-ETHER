"""FAST: git-bus drain writes outbox without Ollama."""

from __future__ import annotations

import json
from pathlib import Path

from core import chat_bus


def test_unanswered_filters_replied() -> None:
    inbox_env = chat_bus.envelope(from_actor="operator", type_="operator", payload={"text": "hi"}, requires_reply=True)
    reply = chat_bus.envelope(
        from_actor="git",
        type_="ack",
        payload={"text": "parked"},
        parent_id=str(inbox_env["id"]),
    )
    waiting = chat_bus.unanswered([inbox_env], [reply])
    assert waiting == []


def test_tick_once_writes_git_ack(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(chat_bus, "ROOT", tmp_path)
    monkeypatch.setattr(chat_bus, "CHAT", tmp_path / "artifacts" / "chat")
    monkeypatch.setattr(chat_bus, "INBOX", tmp_path / "artifacts" / "chat" / "inbox")
    monkeypatch.setattr(chat_bus, "OUTBOX", tmp_path / "artifacts" / "chat" / "outbox")
    monkeypatch.setattr(chat_bus, "ARCHIVE", tmp_path / "artifacts" / "chat" / "archive")
    monkeypatch.setattr(chat_bus, "PENDING_HOST", tmp_path / "artifacts" / "chat" / "pending_host.json")
    monkeypatch.delenv("ETHER_CHAT_LLM", raising=False)
    src = chat_bus.envelope(
        from_actor="grok",
        type_="operator",
        payload={"text": "Status of host and Wave A."},
        job_id="p3_31_skip_llm",
        requires_reply=True,
    )
    chat_bus.send(src, to_grok=False)
    result = chat_bus.tick_once()
    assert result["ok"] is True
    assert result["wrote"] is True
    assert result["from"] == "git"
    assert result["parent_id"] == src["id"]
    outbox = chat_bus.receive(from_grok=False, limit=10)
    assert any(e.get("parent_id") == src["id"] for e in outbox)
    pending = json.loads((tmp_path / "artifacts" / "chat" / "pending_host.json").read_text(encoding="utf-8"))
    assert pending["envelope_id"] == src["id"]
    assert pending["status"] == "acked"


def test_tick_once_caught_up(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(chat_bus, "ROOT", tmp_path)
    monkeypatch.setattr(chat_bus, "CHAT", tmp_path / "artifacts" / "chat")
    monkeypatch.setattr(chat_bus, "INBOX", tmp_path / "artifacts" / "chat" / "inbox")
    monkeypatch.setattr(chat_bus, "OUTBOX", tmp_path / "artifacts" / "chat" / "outbox")
    monkeypatch.setattr(chat_bus, "ARCHIVE", tmp_path / "artifacts" / "chat" / "archive")
    monkeypatch.setattr(chat_bus, "PENDING_HOST", tmp_path / "artifacts" / "chat" / "pending_host.json")
    result = chat_bus.tick_once()
    assert result["ok"] is True
    assert result["wrote"] is False
    assert result["reason"] == "caught up"


def test_summary_and_pending_schema(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(chat_bus, "ROOT", tmp_path)
    monkeypatch.setattr(chat_bus, "CHAT", tmp_path / "artifacts" / "chat")
    monkeypatch.setattr(chat_bus, "INBOX", tmp_path / "artifacts" / "chat" / "inbox")
    monkeypatch.setattr(chat_bus, "OUTBOX", tmp_path / "artifacts" / "chat" / "outbox")
    monkeypatch.setattr(chat_bus, "ARCHIVE", tmp_path / "artifacts" / "chat" / "archive")
    monkeypatch.setattr(chat_bus, "PENDING_HOST", tmp_path / "artifacts" / "chat" / "pending_host.json")
    path = chat_bus.write_pending_host("chat_1", "hello", status="queued")
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["schema"] == "ether_pending_host_v1"
    snap = chat_bus.summary()
    assert "inbox_n" in snap
