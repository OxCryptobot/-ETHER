"""LangGraph-based Selenite planner skeleton (v0.2).

This module is intentionally incomplete. It defines the graph shape we will
implement next without breaking the current rule-based planner.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

# Placeholder structure for future LangGraph integration.
# Avoid hard dependency failures if langgraph isn't installed in minimal envs.

try:
    from langgraph.graph import StateGraph, END
except Exception:  # pragma: no cover
    StateGraph = None  # type: ignore
    END = None  # type: ignore


class PlanState(TypedDict):
    objective: str
    steps: list
    notes: str


def build_plan_graph():
    """Return a compiled LangGraph planner when available."""
    if StateGraph is None:
        raise RuntimeError("langgraph is not available")

    def draft(state: PlanState) -> PlanState:
        # TODO: call Rose Quartz / local model to draft steps
        return state

    def critique(state: PlanState) -> PlanState:
        # TODO: self-critique loop
        return state

    g = StateGraph(PlanState)
    g.add_node("draft", draft)
    g.add_node("critique", critique)
    g.set_entry_point("draft")
    g.add_edge("draft", "critique")
    g.add_edge("critique", END)
    return g.compile()
