"""Selenite — hierarchical planner."""

from __future__ import annotations

import os
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
    RoseQuartzRequest,
    ChatMessage,
)


class Selenite:
    """Hierarchical planner.

    Default: fast rule-based plans.
    Optional: set ETHER_LLM_PLAN=1 to ask Rose Quartz for a plan sketch.
    """

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if isinstance(request.payload, SeleniteRequest):
                user_query = request.payload.user_query
                max_depth = request.payload.max_plan_depth
            else:
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                user_query = data.get("user_query", str(request.payload))
                max_depth = data.get("max_plan_depth", 5)

            if os.getenv("ETHER_LLM_PLAN", "0") == "1":
                plan = self._llm_plan(user_query, max_depth) or self._create_plan(user_query, max_depth)
            else:
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

    def _llm_plan(self, query: str, max_depth: int) -> ExecutionPlan | None:
        """Best-effort LLM plan sketch; falls back silently."""
        try:
            from gems.rose_quartz import RoseQuartz
            from uuid import uuid4

            rq = RoseQuartz()
            prompt = (
                "Return a short numbered implementation plan (max "
                f"{max_depth} steps) for this coding task. One line per step.\nTask: {query}"
            )
            env = Envelope(
                task_id=uuid4(),
                target_gem="rose-quartz",
                payload=RoseQuartzRequest(messages=[ChatMessage(role="user", content=prompt)]),
            )
            res = rq.execute(env)
            if res.error or not res.payload:
                return None
            text = getattr(res.payload, "content", "")
            steps: List[PlanStep] = []
            for i, line in enumerate(text.splitlines(), start=1):
                line = line.strip(" -	")
                if not line:
                    continue
                # strip leading numbers
                while line and (line[0].isdigit() or line[0] in ".):"):
                    line = line[1:].strip()
                if line:
                    steps.append(PlanStep(id=len(steps)+1, action="step", target="code", description=line[:200]))
                if len(steps) >= max_depth:
                    break
            if not steps:
                return None
            return ExecutionPlan(steps=steps, reasoning="LLM-assisted plan")
        except Exception:
            return None

    def _create_plan(self, query: str, max_depth: int) -> ExecutionPlan:
        q = query.lower()
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
        return ExecutionPlan(steps=steps[:max_depth], reasoning=f"Plan for: {query[:120]}")
