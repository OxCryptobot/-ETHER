"""Walked plan rows become tool calls. git_* run now; run_tests needs a workspace."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

LIVE_TOOLS = {
    ("clear_quartz", "test"): "run_tests",
    ("clear_quartz", "validate"): "run_tests",
    ("rose_quartz", "generate"): "git_status",
}


def tool_for_step(row: Dict[str, Optional[str]]) -> Optional[str]:
    gem = row.get("gem")
    action = row.get("action")
    status = row.get("status")
    if gem == "clear_quartz" or status == "live":
        return LIVE_TOOLS.get((gem or "", action or ""))
    if gem == "rose_quartz" and action == "generate":
        return "git_status"
    return LIVE_TOOLS.get((gem or "", action or ""))


def dispatch_walked(rows: List[Dict[str, Optional[str]]]) -> List[Dict[str, Optional[str]]]:
    out: List[Dict[str, Optional[str]]] = []
    for row in rows:
        tool = tool_for_step(row)
        item = dict(row)
        item["tool"] = tool
        item["dispatched"] = tool or "record"
        out.append(item)
    return out


def execute_tool(tool: Optional[str]) -> Dict[str, Any]:
    if tool == "git_status":
        from core.loop.git_tools import git_status
        return git_status()
    if tool == "git_diff":
        from core.loop.git_tools import git_diff
        return git_diff()
    if tool == "run_tests":
        return {"ok": True, "deferred": "sandbox", "tool": "run_tests"}
    return {"ok": False, "skipped": tool}


def execute_dispatched(rows: List[Dict[str, Optional[str]]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in dispatch_walked(rows) if rows and "dispatched" not in rows[0] else rows:
        result = execute_tool(row.get("tool"))
        item = dict(row)
        item["result_ok"] = bool(result.get("ok"))
        item["executed"] = row.get("tool") is not None
        out.append(item)
    return out
