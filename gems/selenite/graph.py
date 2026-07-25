"""Optional LangGraph planning path for Selenite.

Falls back gracefully if langgraph is missing or graph build fails.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from core.schemas import ExecutionPlan, PlanStep


class PlanState(TypedDict, total=False):
    query: str
    max_depth: int
    intent: str
    steps: List[Dict[str, Any]]
    reasoning: str


def _classify_intent(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ["refactor", "restructure", "clean up"]):
        return "refactor"
    if any(w in q for w in ["add", "implement", "create", "write", "build", "make"]):
        return "implement"
    if any(w in q for w in ["fix", "debug", "error", "bug", "broken"]):
        return "fix"
    if any(w in q for w in ["explain", "what", "how", "document"]):
        return "explain"
    return "general"


def _steps_for_intent(intent: str, max_depth: int) -> List[PlanStep]:
    catalogs = {
        "refactor": [
            PlanStep(id=1, action="analyze", target="codebase", description="Map current structure and dependencies"),
            PlanStep(id=2, action="design", target="target_structure", deps=[1], description="Design improved structure"),
            PlanStep(id=3, action="migrate", target="code", deps=[2], description="Apply refactoring changes"),
            PlanStep(id=4, action="test", target="sandbox", deps=[3], description="Verify behavior unchanged"),
            PlanStep(id=5, action="validate", target="security", deps=[4], description="Security and quality audit"),
        ],
        "implement": [
            PlanStep(id=1, action="analyze", target="codebase", description="Understand current structure"),
            PlanStep(id=2, action="generate", target="code", deps=[1], description="Generate the required code"),
            PlanStep(id=3, action="test", target="sandbox", deps=[2], description="Run in Clear Quartz sandbox"),
            PlanStep(id=4, action="validate", target="security", deps=[3], description="Security and quality check"),
        ],
        "fix": [
            PlanStep(id=1, action="reproduce", target="error", description="Reproduce the issue"),
            PlanStep(id=2, action="diagnose", target="root_cause", deps=[1], description="Find root cause"),
            PlanStep(id=3, action="fix", target="code", deps=[2], description="Apply fix"),
            PlanStep(id=4, action="test", target="sandbox", deps=[3], description="Verify fix in sandbox"),
        ],
        "explain": [
            PlanStep(id=1, action="retrieve", target="context", description="Gather relevant code/docs"),
            PlanStep(id=2, action="synthesize", target="explanation", deps=[1], description="Produce clear explanation"),
        ],
        "general": [
            PlanStep(id=1, action="understand", target="request", description="Parse user intent"),
            PlanStep(id=2, action="respond", target="user", deps=[1], description="Generate response"),
        ],
    }
    return catalogs.get(intent, catalogs["general"])[:max_depth]


def build_plan_with_graph(query: str, max_depth: int = 5) -> Optional[ExecutionPlan]:
    """Try LangGraph StateGraph. Return None to signal caller to use rule planner."""
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None

    def classify(state: PlanState) -> PlanState:
        intent = _classify_intent(state["query"])
        return {**state, "intent": intent, "reasoning": f"LangGraph intent={intent}"}

    def expand(state: PlanState) -> PlanState:
        steps = _steps_for_intent(state.get("intent", "general"), state.get("max_depth", 5))
        return {
            **state,
            "steps": [s.model_dump() for s in steps],
        }

    try:
        g = StateGraph(PlanState)
        g.add_node("classify", classify)
        g.add_node("expand", expand)
        g.set_entry_point("classify")
        g.add_edge("classify", "expand")
        g.add_edge("expand", END)
        app = g.compile()
        out = app.invoke({"query": query, "max_depth": max_depth})
        steps = [PlanStep(**s) for s in out.get("steps", [])]
        if not steps:
            return None
        return ExecutionPlan(steps=steps, reasoning=out.get("reasoning", "LangGraph plan"))
    except Exception:
        return None
