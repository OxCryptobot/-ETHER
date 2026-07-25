"""LangGraph-based Selenite planner skeleton (v0.2)."""

from __future__ import annotations

from typing import TypedDict, List

try:
    from langgraph.graph import StateGraph, END
except Exception:  # pragma: no cover
    StateGraph = None  # type: ignore
    END = None  # type: ignore


class PlanState(TypedDict):
    objective: str
    steps: List[str]
    notes: str


def draft(state: PlanState) -> PlanState:
    """Draft numbered steps from the objective (stub)."""
    obj = state.get("objective", "")
    state["steps"] = [
        f"Analyze requirements for: {obj[:80]}",
        "Generate implementation",
        "Test in sandbox",
        "Audit security",
    ]
    state["notes"] = "drafted"
    return state


def critique(state: PlanState) -> PlanState:
    """Light self-critique stub."""
    steps = state.get("steps") or []
    if len(steps) < 2:
        steps.append("Add missing validation step")
    state["steps"] = steps
    state["notes"] = (state.get("notes") or "") + ";critiqued"
    return state


def build_plan_graph():
    if StateGraph is None:
        raise RuntimeError("langgraph is not available")
    g = StateGraph(PlanState)
    g.add_node("draft", draft)
    g.add_node("critique", critique)
    g.set_entry_point("draft")
    g.add_edge("draft", "critique")
    g.add_edge("critique", END)
    return g.compile()
