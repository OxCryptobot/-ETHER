"""Phase 4 — MCP-compatible tool schema registry (offline).

Publishes typed tool definitions for future MCP/LSP wire.
Does not open ports. Does not start an MCP server.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase4_mcp_schema.json"


def _tool(name: str, description: str, properties: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def build_registry() -> Dict[str, Any]:
    tools: List[Dict[str, Any]] = [
        _tool(
            "ether.tool_list",
            "List quarantine and persistent tools",
            {},
            [],
        ),
        _tool(
            "ether.tool_run",
            "Run a persistent tool with JSON payload (sandboxed)",
            {
                "name": {"type": "string"},
                "payload": {"type": "object"},
            },
            ["name"],
        ),
        _tool(
            "ether.fabricate_stub",
            "Stub-only tool fabricate into quarantine (no LLM)",
            {
                "name": {"type": "string"},
                "purpose": {"type": "string"},
            },
            ["name", "purpose"],
        ),
        _tool(
            "ether.phase_status",
            "Read phase1/2/3/4 status artifacts",
            {"phase": {"type": "string", "enum": ["1", "2", "3", "4"]}},
            [],
        ),
        _tool(
            "ether.swarm_plan",
            "Plan-only multi-agent task decomposition (no GPU swarm)",
            {
                "objective": {"type": "string"},
                "max_agents": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            ["objective"],
        ),
    ]

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "4",
        "protocol": "mcp-schema-only",
        "server_live": False,
        "n_tools": len(tools),
        "tools": tools,
        "ok": len(tools) >= 5 and False is False,
        "note": "Schema registry only. No MCP HTTP server. Wire behind future flag.",
    }
    payload["ok"] = payload["n_tools"] >= 5 and payload["server_live"] is False
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(build_registry(), indent=2))
