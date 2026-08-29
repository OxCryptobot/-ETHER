"""Memory stack: RAG + graph + LoRA dry. No Ollama. No train."""
from __future__ import annotations

from core.memory_stack import graph_status, lora_status, rag_query, snapshot
from core.observe_breaker import KILL_STREAK, rewrite


def test_rag_returns_hits_or_empty_ok():
    out = rag_query("ToolRuntime edit_lines", k=3)
    assert out.get("ok") is True
    assert out.get("backend") == "bm25_offline"


def test_graph_has_timeout_template():
    g = graph_status()
    assert g.get("ok") is True
    assert "Timeout" in str(g.get("timeout_hint") or "") or "timeout" in str(g.get("timeout_hint") or "").lower()


def test_lora_stays_dry():
    l = lora_status()
    assert l.get("trained") is False
    assert l.get("adapter_written") is False
    assert l.get("mode") == "dry"
    assert l.get("ready_for_real_train") is False


def test_snapshot_writes():
    snap = snapshot()
    assert snap.get("soft_launch") is False
    assert snap.get("path")
    assert snap.get("lora", {}).get("trained") is False


def test_observe_breaker_rewrites_then_kills():
    sub = rewrite("read_file", 3)
    assert sub is not None and sub["tool"] == "bug_comments"
    kill = rewrite("read_file", KILL_STREAK)
    assert kill is not None and kill["tool"] == "done"
