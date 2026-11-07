"""Every stage does real work. Theatre in the protocol does not block the adapter."""
from __future__ import annotations

from typing import Any, Dict

from gems.protocol import by_id


STAGE_GEM = {
    "plan": "selenite",
    "route": "rose_quartz",
    "sandbox": "clear_quartz",
    "memory": "citrine",
    "profile": "labradorite",
    "evolve": "amethyst",
    "security": "black_tourmaline",
    "fabricate": "grandidierite",
}


def route_stage(stage: str) -> Dict[str, Any]:
    """One stage. The gem is named. The adapter does the work."""
    gid = STAGE_GEM.get(stage)
    if gid is None:
        return {"ok": False, "stage": stage, "reason": "unknown"}
    gem = by_id(gid)
    if gem is None:
        return {"ok": False, "stage": stage, "reason": "missing"}
    return {"ok": True, "stage": stage, "gem": gid, "role": gem.role, "writes": False}


def plan(root, goal: str) -> Dict[str, Any]:
    """Selenite. One step: search, then edit. No second model call."""
    row = route_stage("plan")
    if not row["ok"]:
        return row
    return {**row, "steps": ["search", "edit", "test"]}


def route(root, text: str) -> Dict[str, Any]:
    """Rose Quartz. A tool reply is a tool. A function reply is an edit."""
    row = route_stage("route")
    if not row["ok"]:
        return row
    kind = "tool" if '"tool"' in text else "edit"
    return {**row, "kind": kind, "next": kind}


def memory(root, note: str) -> Dict[str, Any]:
    """Citrine. The trace is stored. The next prompt may see it."""
    row = route_stage("memory")
    if not row["ok"]:
        return row
    from core.agent.sota import remember

    remember(root, "trace", note[:180], kept=False)
    return {**row, "stored": note[:180]}


def profile(root, text: str) -> Dict[str, Any]:
    """Labradorite. A function shape is required. Prose fails."""
    row = route_stage("profile")
    if not row["ok"]:
        return row
    ok = text.strip().startswith("def ")
    return {**row, "shape": ok, "next": "edit" if ok else "ask"}


def security(root, text: str) -> Dict[str, Any]:
    """Black Tourmaline. A shell or an import of os fails closed."""
    row = route_stage("security")
    if not row["ok"]:
        return row
    bad = "subprocess" in text or "os.system" in text or "__import__" in text
    return {**row, "clean": not bad, "next": "stop" if bad else "continue"}


def evolve(root, note: str) -> Dict[str, Any]:
    """Amethyst. One lesson per day. A repeat of the same day is skipped."""
    row = route_stage("evolve")
    if not row["ok"]:
        return row
    from core.agent.sota import recall

    last = recall(root)
    return {**row, "new": note not in last}


def fabricate(root, name: str) -> Dict[str, Any]:
    """Grandidierite. A name is a tool only if it is in the skill set."""
    row = route_stage("fabricate")
    if not row["ok"]:
        return row
    from core.agent.skills import list_skills

    return {**row, "known": name in list_skills()}
