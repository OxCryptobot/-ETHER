"""Map a walked plan step onto a ToolRuntime tool name.

Live gem + test/validate → run_tests. Everything else is recorded, not executed.
This is the Phase-3/4 bridge: plan_walk output becomes a tool intent.
"""
from __future__ import annotations

from typing import Dict, List, Optional

LIVE_TOOLS = {
    ("clear_quartz", "test"): "run_tests",
    ("clear_quartz", "validate"): "run_tests",
    ("black_tourmaline", "validate"): None,  # caps exist; no extra tool
}


def tool_for_step(row: Dict[str, Optional[str]]) -> Optional[str]:
    gem = row.get("gem")
    action = row.get("action")
    status = row.get("status")
    if status != "live" and gem != "clear_quartz":
        return None
    return LIVE_TOOLS.get((gem or "", action or ""))


def dispatch_walked(rows: List[Dict[str, Optional[str]]]) -> List[Dict[str, Optional[str]]]:
    out: List[Dict[str, Optional[str]]] = []
    for row in rows:
        tool = tool_for_step(row)
        item = dict(row)
        item["tool"] = tool
        item["dispatched"] = "run_tests" if tool == "run_tests" else "record"
        out.append(item)
    return out
