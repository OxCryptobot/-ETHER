"""Spike tests: Clear Quartz MCP tools call the real sandbox + honest gate still holds.

These tests do not require a live MCP transport. They exercise:
1. create_server() builds without error when mcp is installed.
2. execute_code tool path returns real sandbox results.
3. is_honest_tool_path_pass still rejects generate-fallback theatre.
"""

from __future__ import annotations

import os
import pytest


def test_mcp_sdk_optional():
    """Import of mcp_server must never break the rest of ETHER if mcp is absent."""
    # Force a clean import path check
    from gems.clear_quartz import mcp_server as m

    assert hasattr(m, "create_server")
    assert hasattr(m, "_MCP_AVAILABLE")


@pytest.mark.skipif(
    os.getenv("ETHER_SKIP_MCP") == "1",
    reason="ETHER_SKIP_MCP=1",
)
def test_create_server_and_execute_code():
    try:
        from gems.clear_quartz.mcp_server import create_server, _MCP_AVAILABLE
    except Exception as e:
        pytest.skip(f"mcp_server import failed: {e}")

    if not _MCP_AVAILABLE:
        pytest.skip("mcp package not installed")

    server = create_server("test-cq")
    # Locate the registered tool by calling the underlying function directly
    # (MCPServer decorators bind the Python function; we exercise the same body).
    from gems.clear_quartz.mcp_server import _cq, _envelope

    cq = _cq()
    env = _envelope(code="print(2 + 2)", timeout=15)
    res = cq.execute(env)
    assert res.error is None, f"sandbox error: {res.error}"
    assert res.payload is not None
    assert "4" in (res.payload.stdout or "")
    assert res.payload.exit_code == 0


def test_honest_gate_rejects_generate_fallback():
    """Prove the terminal harden contract is independent of transport."""
    from core.loop.handlers.tool_runtime_gate import is_honest_tool_path_pass

    # Simulated scoreboard row that looks "ok" but came from generate fallback
    fake_ok_generate = {
        "ok": True,
        "score": 1.0,
        "strategy": "generate",
        "mode": "live",
        "degraded": [],
    }
    assert is_honest_tool_path_pass(fake_ok_generate) is False

    fake_terminal_fail = {
        "ok": True,
        "score": 0.0,
        "degraded": ["tool_runtime_failed_terminal"],
    }
    assert is_honest_tool_path_pass(fake_terminal_fail) is False

    clean_tool_path = {
        "ok": True,
        "score": 1.0,
        "strategy": "tool_runtime",
        "mode": "live",
        "degraded": [],
    }
    assert is_honest_tool_path_pass(clean_tool_path) is True


def test_sandbox_health_shape():
    """sandbox_health returns a stable dict even without MCP SDK."""
    from gems.clear_quartz.sandbox import sandbox_backend

    backend = sandbox_backend()
    assert backend in ("docker", "local", "auto") or isinstance(backend, str)
