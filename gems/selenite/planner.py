"""Selenite — hierarchical planner."""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
)


class PlanStep(BaseModel):
    id: int
    action: str
    target: str
    deps: List[int] = Field(default_factory=list)
    description: str = ""


class ExecutionPlan(BaseModel):
    steps: List[PlanStep] = Field(default_factory=list)
    reasoning: str = ""


class SeleniteRequest(BaseModel):
    user_query: str
    available_tools: List[str] = Field(default_factory=list)
    context: List[Dict[str, Any]] = Field(default_factory=list)
    max_plan_depth: int = 5


class SeleniteResponse(BaseModel):
    plan: ExecutionPlan
    needs_tool: bool = False
    tool_request: Optional[Dict[str, Any]] = None
    confidence_score: float = 0.7


class Selenite:
    """Hierarchical planner gem.

    Current version: rule-based + structured plan output.
    Next version will integrate full LangGraph ReAct loop.
    """

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            # Accept both typed and dict payloads for now
            if hasattr(request.payload, "model_dump"):
                data = request.payload.model_dump()
            elif isinstance(request.payload, dict):
                data = request.payload
            else:
                data = {"user_query": str(request.payload)}

            user_query = data.get("user_query", "")

            # Very simple planning logic for the foundation
            plan = self._create_basic_plan(user_query)

            response_payload = SeleniteResponse(
                plan=plan,
                needs_tool=False,
                confidence_score=0.65,
            )

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="selenite",
                payload=response_payload,  # type: ignore[arg-type]
            )

        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="selenite",
                error=GemError(
                    type=GemErrorType.RUNTIME,
                    message=str(e),
                    recoverable=True,
                ),
            )

    def _create_basic_plan(self, query: str) -> ExecutionPlan:
        """Generate a simple structured plan from the user query."""
        query_lower = query.lower()

        steps: List[PlanStep] = []

        if any(word in query_lower for word in ["add", "implement", "create", "write"]):
            steps = [
                PlanStep(id=1, action="analyze", target="codebase", description="Understand current structure"),
                PlanStep(id=2, action="generate", target="code", description="Generate the required code", deps=[1]),
                PlanStep(id=3, action="test", target="sandbox", description="Run in Clear Quartz sandbox", deps=[2]),
                PlanStep(id=4, action="validate", target="security", description="Security and quality check", deps=[3]),
            ]
        elif any(word in query_lower for word in ["fix", "debug", "error", "bug"]):
            steps = [
                PlanStep(id=1, action="reproduce", target="error", description="Reproduce the issue"),
                PlanStep(id=2, action="diagnose", target="root_cause", description="Find root cause", deps=[1]),
                PlanStep(id=3, action="fix", target="code", description="Apply fix", deps=[2]),
                PlanStep(id=4, action="test", target="sandbox", description="Verify fix in sandbox", deps=[3]),
            ]
        else:
            steps = [
                PlanStep(id=1, action="understand", target="request", description="Parse user intent"),
                PlanStep(id=2, action="respond", target="user", description="Generate response", deps=[1]),
            ]

        return ExecutionPlan(
            steps=steps,
            reasoning=f"Generated basic plan for query: {query[:80]}...",
        )
