"""Selenite — hierarchical planner."""

from __future__ import annotations

import os
import re
from typing import List, Optional, Dict, Any

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
    """Hierarchical planner with optional tool_request intents."""

    def execute(self, request: Envelope) -> ResponseEnvelope:
        try:
            if isinstance(request.payload, SeleniteRequest):
                user_query = request.payload.user_query
                max_depth = request.payload.max_plan_depth
                available_tools = list(request.payload.available_tools or [])
            else:
                data = request.payload.model_dump() if hasattr(request.payload, "model_dump") else {}
                user_query = data.get("user_query", str(request.payload))
                max_depth = data.get("max_plan_depth", 5)
                available_tools = list(data.get("available_tools") or [])

            plan: ExecutionPlan | None = None

            if os.getenv("ETHER_LANGGRAPH", "0") == "1":
                try:
                    from gems.selenite.graph import build_plan_with_graph

                    plan = build_plan_with_graph(user_query, max_depth)
                except Exception:
                    plan = None

            if plan is None and os.getenv("ETHER_LLM_PLAN", "0") == "1":
                plan = self._llm_plan(user_query, max_depth)

            if plan is None:
                plan = self._create_plan(user_query, max_depth)

            needs_tool, tool_request = self._detect_tool_intent(user_query, available_tools)

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="selenite",
                payload=SeleniteResponse(
                    plan=plan,
                    needs_tool=needs_tool,
                    tool_request=tool_request,
                    confidence_score=0.75 if needs_tool else 0.7,
                ),
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="selenite",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )

    def _detect_tool_intent(
        self, query: str, available_tools: List[str]
    ) -> tuple[bool, Optional[Dict[str, Any]]]:
        q = query.lower().strip()

        # explicit fabricate
        m = re.search(
            r"(?:fabricate|create|build|make)\s+(?:a\s+)?tool\s+(?:named\s+|called\s+)?([a-zA-Z_][\w]*)",
            q,
        )
        if m or "fabricate tool" in q or "new tool" in q:
            name = m.group(1) if m else "auto_tool"
            return True, {
                "action": "fabricate",
                "name": name,
                "docstring": query[:240],
                "purpose": query[:240],
            }

        # run existing tool by name
        m2 = re.search(r"(?:run|use)\s+tool\s+([a-zA-Z_][\w]*)", q)
        if m2:
            return True, {"action": "run", "name": m2.group(1), "payload": {}}

        # generate stub
        if "generate tool" in q or "scaffold tool" in q:
            return True, {
                "action": "generate",
                "name": "scaffolded_tool",
                "docstring": query[:200],
            }

        # if available_tools mentions and query asks to use one
        for t in available_tools:
            tname = t.replace(".py", "")
            if tname.lower() in q and any(w in q for w in ("use", "run", "call")):
                return True, {"action": "run", "name": tname, "payload": {}}

        return False, None

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
        try:
            from gems.selenite.graph import _classify_intent, _steps_for_intent

            intent = _classify_intent(query)
            steps = _steps_for_intent(intent, max_depth)
            return ExecutionPlan(steps=steps, reasoning=f"Rule plan intent={intent}: {query[:100]}")
        except Exception:
            pass

        steps = [
            PlanStep(id=1, action="understand", target="request", description="Parse user intent"),
            PlanStep(id=2, action="respond", target="user", deps=[1], description="Generate response"),
        ]
        return ExecutionPlan(steps=steps[:max_depth], reasoning=f"Plan for: {query[:120]}")
