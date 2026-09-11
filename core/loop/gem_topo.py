"""Gem topography. ETHER is the gems. They walk the agentic cycle in order."""
from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

from core.registry import build_default_registry
from core.schemas import (
    AmethystRequest,
    BlackTourmalineRequest,
    ClearQuartzRequest,
    CitrineRequest,
    Envelope,
    GrandidieriteRequest,
    LabradoriteRequest,
    SeleniteRequest,
)

# Permanent order. Do not shuffle.
TOPO: List[str] = [
    "selenite",
    "citrine",
    "rose-quartz",
    "clear-quartz",
    "black-tourmaline",
    "labradorite",
    "amethyst",
    "grandidierite",
]


def _one(registry: Any, name: str, payload: Any, timeout: int = 20) -> Dict[str, Any]:
    env = Envelope(task_id=uuid4(), target_gem=name, payload=payload, timeout_seconds=timeout)
    try:
        res = registry.execute(env)
        err = None if res.error is None else str(res.error.message)[:160]
        return {"gem": name, "ok": res.error is None, "error": err}
    except Exception as exc:
        return {"gem": name, "ok": False, "error": f"{type(exc).__name__}:{exc}"[:160]}


def walk_gems(objective: str = "agentic ping") -> Dict[str, Any]:
    """Walk every gem once. Rose is listed; LLM call is skipped in FAST walk."""
    registry = build_default_registry()
    present = set(registry.list_gems())
    rows: List[Dict[str, Any]] = []
    tiny = "def ping():\n    return 1\n"
    payloads = {
        "selenite": SeleniteRequest(user_query=objective, available_tools=["bug_comments", "replace_once", "run_tests"]),
        "citrine": CitrineRequest(action="health"),
        "clear-quartz": ClearQuartzRequest(code=tiny, objective=objective, prepare_code=False, test_args=[]),
        "black-tourmaline": BlackTourmalineRequest(artifact=tiny),
        "labradorite": LabradoriteRequest(code=tiny),
        "amethyst": AmethystRequest(action="log", interaction={"objective": objective}),
        "grandidierite": GrandidieriteRequest(tool_request={"name": "ping", "stub_only": True}),
    }
    for name in TOPO:
        if name == "rose-quartz":
            rows.append({"gem": name, "ok": name in present, "error": None, "note": "registered; no FAST LLM call"})
            continue
        if name not in present:
            rows.append({"gem": name, "ok": False, "error": "unregistered"})
            continue
        rows.append(_one(registry, name, payloads[name]))
    return {
        "ok": all(r.get("ok") for r in rows if r.get("gem") != "clear-quartz"),
        "n": len(rows),
        "present": sorted(present),
        "rows": rows,
        "cycle": "observe-tool-sandbox-critique-memory",
        "note": "ETHER is the gems. This is the topography walk.",
    }
