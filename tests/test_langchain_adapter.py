"""LangChain adapter works without langchain installed."""
from __future__ import annotations

from core.langchain_adapter import available, invoke_tool, run_chain, snapshot, tool_specs
from core.phase3_complete import compute
from core.unleash_check import evaluate


def test_tools_listed():
    names = {t["name"] for t in tool_specs()}
    assert "rag_search" in names
    assert "propose" in names


def test_chain_does_not_require_langchain():
    out = run_chain("anchor_edit ledger")
    assert "langchain_installed" in out
    assert out.get("langchain_installed") is available()


def test_graph_hint_tool():
    out = invoke_tool("graph_hint", {"stderr": "Timeout"})
    assert out.get("ok") is True
    assert out.get("hint")


def test_snapshot_and_boards():
    snap = snapshot()
    assert snap.get("replaces_gems") is False
    assert snap.get("soft_launch") is False
    board = compute()
    assert board.get("pct") >= 80
    u = evaluate()
    assert u.get("unleash_ready") is False or isinstance(u.get("blocked"), list)
    assert "operator_env" in u
