"""Ollama-native tool schema. JSON scrape stays until the 4B speaks tools."""
from __future__ import annotations

from typing import Any, Dict, List

from core.tool_runtime import TOOL_SPECS


def ollama_tools() -> List[Dict[str, Any]]:
    tools: List[Dict[str, Any]] = []
    for spec in TOOL_SPECS:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": spec["name"],
                    "description": spec["doc"],
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": True},
                },
            }
        )
    return tools


def schema_ok() -> bool:
    names = {t["function"]["name"] for t in ollama_tools()}
    return "read_file" in names and "run_tests" in names and "git_status" in names
