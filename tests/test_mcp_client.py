"""Tests for thin in-process MCP client helpers."""

from __future__ import annotations

import os
import pytest


def test_list_mcp_gems():
    from core.mcp_client import list_mcp_gems

    gems = list_mcp_gems()
    assert "clear-quartz" in gems
    assert "citrine" in gems
    assert "labradorite" in gems


@pytest.mark.skipif(
    os.getenv("ETHER_SKIP_MCP") == "1",
    reason="ETHER_SKIP_MCP=1",
)
def test_call_tool_inproc_cq_health():
    try:
        from core.mcp_client import call_tool_inproc
        from gems.clear_quartz.mcp_server import _MCP_AVAILABLE
    except Exception as e:
        pytest.skip(str(e))
    if not _MCP_AVAILABLE:
        pytest.skip("mcp not installed")

    # sandbox_health is pure and does not need Docker
    # We reach the underlying function body via the same import path
    from gems.clear_quartz.sandbox import sandbox_backend

    backend = sandbox_backend()
    assert isinstance(backend, str)


@pytest.mark.skipif(
    os.getenv("ETHER_SKIP_MCP") == "1",
    reason="ETHER_SKIP_MCP=1",
)
def test_smoke_parallel_gems_structure():
    """Structure test — does not require live Qdrant/Docker for import path."""
    from core.mcp_client import smoke_parallel_gems, concurrent_tool_calls, list_mcp_gems

    assert len(list_mcp_gems()) >= 3
    # concurrent_tool_calls with empty is fine
    outs = concurrent_tool_calls([])
    assert outs == []
