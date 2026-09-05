"""Persistent tool names for Selenite. Fail-visible when the registry is down."""
from __future__ import annotations

from typing import Any, List


def available_tools(result: Any) -> List[str]:
    try:
        from gems.grandidierite.registry import list_tools

        return [n.replace(".py", "") for n in list_tools().get("persistent", [])]
    except Exception as exc:
        result.degraded.append(f"grandidierite_list_tools_unavailable:{type(exc).__name__}")
        return []
