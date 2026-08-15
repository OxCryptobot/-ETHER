"""Thin MCP client helpers for ETHER Orchestrator / ToolRuntime.

Local-first: prefer in-process calls against the gem MCPServer instances
(no stdio spawn overhead). Fallback to stdio Client only when a remote
or external MCP server is required.

Honest gate and train_gates stay upstream of any tool result.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Callable, Dict, List, Optional, Tuple


def _cq_server():
    from gems.clear_quartz.mcp_server import create_server, _MCP_AVAILABLE

    if not _MCP_AVAILABLE:
        raise RuntimeError("mcp not installed")
    return create_server("ether-clear-quartz-inproc")


def _citrine_server():
    from gems.citrine.mcp_server import create_server, _MCP_AVAILABLE

    if not _MCP_AVAILABLE:
        raise RuntimeError("mcp not installed")
    return create_server("ether-citrine-inproc")


def _lab_server():
    from gems.labradorite.mcp_server import create_server, _MCP_AVAILABLE

    if not _MCP_AVAILABLE:
        raise RuntimeError("mcp not installed")
    return create_server("ether-labradorite-inproc")


# Registry of in-process server factories (expand as gems grow)
_SERVER_FACTORIES: Dict[str, Callable[[], Any]] = {
    "clear-quartz": _cq_server,
    "citrine": _citrine_server,
    "labradorite": _lab_server,
}


def list_mcp_gems() -> List[str]:
    return sorted(_SERVER_FACTORIES.keys())


def call_tool_inproc(gem: str, tool_name: str, **kwargs: Any) -> Dict[str, Any]:
    """Call a registered MCP tool on the in-process server for `gem`.

    Returns the tool result dict. Raises on missing gem/tool or MCP absent.
    """
    factory = _SERVER_FACTORIES.get(gem)
    if factory is None:
        raise KeyError(f"No MCP server factory for gem={gem!r}. Known: {list_mcp_gems()}")
    server = factory()
    # MCPServer exposes tools via internal registry; the decorated functions
    # are bound. For 2026-07-28 SDK we reach the underlying callable.
    # Prefer public API if present, else fall back to attribute lookup.
    tool_fn = None
    if hasattr(server, "get_tool"):
        tool_fn = server.get_tool(tool_name)
    if tool_fn is None:
        # Decorator attaches the function under the tool name on the instance
        # or in a _tools map depending on SDK minor; try common paths.
        tools = getattr(server, "_tools", None) or getattr(server, "tools", None) or {}
        if isinstance(tools, dict):
            entry = tools.get(tool_name)
            if entry is not None:
                tool_fn = getattr(entry, "fn", entry) if not callable(entry) else entry
        if tool_fn is None and hasattr(server, tool_name):
            tool_fn = getattr(server, tool_name)
    if tool_fn is None or not callable(tool_fn):
        raise AttributeError(f"Tool {tool_name!r} not found on {gem} MCP server")
    result = tool_fn(**kwargs)
    if isinstance(result, dict):
        return result
    return {"ok": True, "result": result}


def concurrent_tool_calls(
    calls: List[Tuple[str, str, Dict[str, Any]]],
    max_workers: int = 4,
) -> List[Dict[str, Any]]:
    """Run multiple (gem, tool_name, kwargs) tool calls concurrently.

    Used by swarm_parallel_gems_smoke under training wheels.
    Returns list of result dicts in same order as `calls`.
    """
    results: List[Optional[Dict[str, Any]]] = [None] * len(calls)

    def _one(idx: int, gem: str, tool: str, kw: Dict[str, Any]) -> None:
        try:
            results[idx] = call_tool_inproc(gem, tool, **kw)
        except Exception as e:
            results[idx] = {"ok": False, "error": str(e), "gem": gem, "tool": tool}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [
            ex.submit(_one, i, gem, tool, kw)
            for i, (gem, tool, kw) in enumerate(calls)
        ]
        concurrent.futures.wait(futs)

    return [r or {"ok": False, "error": "missing"} for r in results]


def smoke_parallel_gems() -> Dict[str, Any]:
    """Minimal concurrent MCP smoke used by swarm jobs.

    Calls:
      - clear-quartz.sandbox_health
      - citrine.memory_health
      - labradorite.profile_complexity (tiny snippet)
    """
    calls = [
        ("clear-quartz", "sandbox_health", {}),
        ("citrine", "memory_health", {}),
        ("labradorite", "profile_complexity", {"code": "def f(x): return x\n"}),
    ]
    outs = concurrent_tool_calls(calls, max_workers=3)
    return {
        "ok": all(o.get("ok") for o in outs if isinstance(o, dict)),
        "n": len(outs),
        "results": outs,
    }
