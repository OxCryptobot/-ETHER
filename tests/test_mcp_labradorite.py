"""Spike tests: Labradorite MCP tools call the real critique path."""

from __future__ import annotations

import os
import pytest


def test_mcp_sdk_optional():
    from gems.labradorite import mcp_server as m

    assert hasattr(m, "create_server")
    assert hasattr(m, "_MCP_AVAILABLE")


@pytest.mark.skipif(
    os.getenv("ETHER_SKIP_MCP") == "1",
    reason="ETHER_SKIP_MCP=1",
)
def test_create_server_and_critique():
    try:
        from gems.labradorite.mcp_server import create_server, _MCP_AVAILABLE, _lab, _envelope
    except Exception as e:
        pytest.skip(f"mcp_server import failed: {e}")

    if not _MCP_AVAILABLE:
        pytest.skip("mcp package not installed")

    server = create_server("test-lab")
    assert server is not None

    lab = _lab()
    env = _envelope(code="def add(a, b):\n    return a + b\n")
    res = lab.execute(env)
    assert res.error is None
    assert res.payload is not None
    assert hasattr(res.payload, "critique")
    assert res.payload.complexity_score >= 0.0
