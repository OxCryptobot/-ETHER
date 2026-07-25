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
            for line in text.splitlines():
                line = line.strip(" -\t")
                if not line:
                    continue
                while line and (line[0].isdigit() or line[0] in ".):"):
                    line = line[1:].strip()
                if line:
                    steps.append(
                        PlanStep(
                            id=len(steps) + 1,
                            action="step",
                            target="code",
                            description=line[:200],
                        )
                    )
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
                PlanStep(id=1, action="analyze", target="codebase", description="Map current structure and dependencies"),
                PlanStep(id=2, action="design", target="target_structure", deps=[1], description="Design improved structure"),
                PlanStep(id=3, action="migrate", target="code", deps=[2], description="Apply refactoring changes"),
                PlanStep(id=4, action="test", target="sandbox", deps=[3], description="Verify behavior unchanged"),
                PlanStep(id=5, action="validate", target="security", deps=[4], description="Security and quality audit"),
            ]
        elif any(w in q for w in ["add", "implement", "create", "write", "build", "make"]):
            steps = [
                PlanStep(id=1, action="analyze", target="codebase", description="Understand current structure"),
                PlanStep(id=2, action="generate", target="code", deps=[1], description="Generate the required code"),
                PlanStep(id=3, action="test", target="sandbox", deps=[2], description="Run in Clear Quartz sandbox"),
                PlanStep(id=4, action="validate", target="security", deps=[3], description="Security and quality check"),
            ]
        elif any(w in q for w in ["fix", "debug", "error", "bug", "broken"]):
            steps = [
                PlanStep(id=1, action="reproduce", target="error", description="Reproduce the issue"),
                PlanStep(id=2, action="diagnose", target="root_cause", deps=[1], description="Find root cause"),
                PlanStep(id=3, action="fix", target="code", deps=[2], description="Apply fix"),
                PlanStep(id=4, action="test", target="sandbox", deps=[3], description="Verify fix in sandbox"),
            ]
        elif any(w in q for w in ["explain", "what", "how", "document"]):
            steps = [
                PlanStep(id=1, action="retrieve", target="context", description="Gather relevant code/docs"),
                PlanStep(id=2, action="synthesize", target="explanation", deps=[1], description="Produce clear explanation"),
            ]
        else:
            steps = [
                PlanStep(id=1, action="understand", target="request", description="Parse user intent"),
                PlanStep(id=2, action="respond", target="user", deps=[1], description="Generate response"),
            ]
        return ExecutionPlan(steps=steps[:max_depth], reasoning=f"Plan for: {query[:120]}")
