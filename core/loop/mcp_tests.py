"""Clear Quartz MCP → pytest. Falls back to living.run_tests if MCP is absent."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def run_tests_mcp(workspace: Optional[Path] = None, code: Optional[str] = None) -> Dict[str, Any]:
    try:
        from core.mcp_client import call_tool_inproc

        payload: Dict[str, Any] = {}
        if workspace is not None:
            payload["workspace"] = str(workspace)
        if code is not None:
            payload["code"] = code
        out = call_tool_inproc("clear_quartz", "run_tests", **payload)
        if isinstance(out, dict):
            out.setdefault("via", "mcp_clear_quartz")
            return out
    except Exception as exc:
        fallback = {"ok": False, "via": "mcp_clear_quartz", "error": type(exc).__name__}
        from core.loop.living import run_tests

        live = run_tests(workspace=workspace, code=code)
        live["mcp_fallback"] = fallback
        live["via"] = live.get("via") or "living"
        return live
    from core.loop.living import run_tests

    return run_tests(workspace=workspace, code=code)
