"""Selenite — hierarchical planner (improved heuristics)."""

from __future__ import annotations

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
    """Hierarchical planner gem."""

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if isinstance(request.payload, SeleniteRequest):
                user_query = request.payload.user_query
                max_depth = request.payload.max_plan_depth
            else:
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                user_query = data.get("user_query", str(request.payload))
                max_depth = data.get("max_plan_depth", 5)

            plan = self._create_plan(user_query, max_depth)
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="selenite",
                payload=SeleniteResponse(plan=plan, needs_tool=False, confidence_score=0.7),
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="selenite",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )

    def _create_plan(self, query: str, max_depth: int) -> ExecutionPlan:
        q = query.lower()
        steps: list[PlanStep] = []

        if any(w in q for w in ["refactor", "restructure", "clean up"]):
            steps = [
                PlanStep(1, "analyze", "codebase", [], "Map current structure and dependencies"),
                PlanStep(2, "design", "target_structure", [1], "Design improved structure"),
                PlanStep(3, "migrate", "code", [2], "Apply refactoring changes"),
                PlanStep(4, "test", "sandbox", [3], "Verify behavior unchanged"),
                PlanStep(5, "validate", "security", [4], "Security and quality audit"),
            ]
        elif any(w in q for w in ["add", "implement", "create", "write", "build", "make"]):
            steps = [
                PlanStep(1, "analyze", "codebase", [], "Understand current structure"),
                PlanStep(2, "generate", "code", [1], "Generate the required code"),
                PlanStep(3, "test", "sandbox", [2], "Run in Clear Quartz sandbox"),
                PlanStep(4, "validate", "security", [3], "Security and quality check"),
            ]
        elif any(w in q for w in ["fix", "debug", "error", "bug", "broken"]):
            steps = [
                PlanStep(1, "reproduce", "error", [], "Reproduce the issue"),
                PlanStep(2, "diagnose", "root_cause", [1], "Find root cause"),
                PlanStep(3, "fix", "code", [2], "Apply fix"),
                PlanStep(4, "test", "sandbox", [3], "Verify fix in sandbox"),
            ]
        elif any(w in q for w in ["explain", "what", "how", "document"]):
            steps = [
                PlanStep(1, "retrieve", "context", [], "Gather relevant code/docs"),
                PlanStep(2, "synthesize", "explanation", [1], "Produce clear explanation"),
            ]
        else:
            steps = [
                PlanStep(1, "understand", "request", [], "Parse user intent"),
                PlanStep(2, "respond", "user", [1], "Generate response"),
            ]

        return ExecutionPlan(
            steps=steps[:max_depth],
            reasoning=f"Plan for: {query[:120]}",
        )
