"""Batch 10: ETHER's read-only status as an MCP server (stdio, JSON-RPC 2.0, no SDK needed).

Any MCP host (an IDE, the Control Matrix tooling, another agent) can launch
    python -m scripts.mcp_status_server
and read the writer's state without touching it. Every tool is read-only (annotated
readOnlyHint) and only reads files under artifacts/; nothing here writes, starts or stops
anything, so the single-writer rule is unchanged.

Tools:
  ether_health    host_main.json health, worst signal, signals, selfcheck summary, timestamp
  ether_learning  artifacts/learning_summary.json (honest-gate outcomes per arm)
  ether_sota      artifacts/sota.json: last attempt, kept count, next goal
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROTOCOL = "2025-06-18"
MAX_CHARS = 20000


def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parents[1]


def _read(rel: str) -> Dict[str, Any]:
    try:
        data = json.loads((_root() / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"missing": rel}
    return data if isinstance(data, dict) else {"value": data}


def health() -> Dict[str, Any]:
    row = _read("artifacts/host_main.json")
    keep = ("ts", "health", "health_worst", "health_signals", "next_goal", "real_queue", "selfcheck", "missing")
    return {k: row[k] for k in keep if k in row}


def learning() -> Dict[str, Any]:
    return _read("artifacts/learning_summary.json")


def sota() -> Dict[str, Any]:
    row = _read("artifacts/sota.json")
    keep = ("ts", "kept_n", "last", "goal", "note", "ok", "missing")
    small = {k: row[k] for k in keep if k in row}
    return small or {k: row[k] for k in list(row)[:20]}


TOOLS = {
    "ether_health": (health, "ETHER host health: worst signal, signals, selfcheck (read-only)."),
    "ether_learning": (learning, "ETHER learning summary: honest-gate outcomes per arm (read-only)."),
    "ether_sota": (sota, "ETHER last learning attempt and kept count (read-only)."),
}


def tool_list() -> list:
    return [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": {}},
             "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}}
            for n, (_f, d) in TOOLS.items()]


def handle(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One JSON-RPC message in, one response out (None for notifications)."""
    method = msg.get("method")
    rid = msg.get("id")
    if rid is None:
        return None
    if method == "initialize":
        result: Any = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "ether-status", "version": "batch10"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        name = (msg.get("params") or {}).get("name")
        entry = TOOLS.get(str(name))
        if entry is None:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
        text = json.dumps(entry[0](), indent=1, default=str)[:MAX_CHARS]
        result = {"content": [{"type": "text", "text": text}], "isError": False}
    else:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out: Optional[Dict[str, Any]] = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            out = handle(msg) if isinstance(msg, dict) else None
        if out is not None:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
