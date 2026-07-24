"""Selenite — hierarchical planner."""

from __future__ import annotations

from typing import List

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
    SeleniteRequest,
    SeleniteResponse,
    PlanStep,
    ExecutionPlan,
)


class Selenite:
    """Hierarchical planner gem (rule-based foundation)."""

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if not isinstance(request.payload, SeleniteRequest):
                # Allow dict for flexibility during transition
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                user_query = data.get("user_query", str(request.payload))
            else:
                user_query = request.payload.user_query

            plan = self._create_basic_plan(user_query)

            response_payload = SeleniteResponse(
                plan=plan,
                needs_tool=False,
                confidence_score=0.65,
            )

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="selenite",
                payload=response_payload,
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
        query_lower = query.lower()

        if any(w in query_lower for w in ["add", "implement", "create", "write", "build"]):
            steps = [
                PlanStep(id=1, action="analyze", target="codebase", description="Understand current structure"),
                PlanStep(id=2, action="generate", target="code", description="Generate the required code", deps=[1]),
                PlanStep(id=3, action="test", target="sandbox", description="Run in Clear Quartz sandbox", deps=[2]),
                PlanStep(id=4, action="validate", target="security", description="Security and quality check", deps=[3]),
            ]
        elif any(w in query_lower for w in ["fix", "debug", "error", "bug"]):
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
            reasoning=f"Generated plan for: {query[:100]}",
        )
