"""End-to-end pipeline for @ETHER.

Flow:
  plan (Selenite) → code (Rose Quartz) → sandbox (Clear Quartz) → audit (Black Tourmaline)
"""

from __future__ import annotations

from uuid import uuid4, UUID
from typing import Optional, Dict, Any

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    SeleniteRequest,
    SeleniteResponse,
    RoseQuartzRequest,
    RoseQuartzResponse,
    ClearQuartzRequest,
    ClearQuartzResponse,
    BlackTourmalineRequest,
    BlackTourmalineResponse,
    ChatMessage,
    GemError,
    GemErrorType,
)
from core.registry import GemRegistry, build_default_registry
from core.orchestrator import Orchestrator, Status
from core.confidence import compute_clear_quartz_confidence


class PipelineResult(BaseModel):
    task_id: UUID
    objective: str
    plan: Optional[ExecutionPlan] = None
    generated_code: Optional[str] = None
    sandbox: Optional[ClearQuartzResponse] = None
    audit: Optional[BlackTourmalineResponse] = None
    confidence: float = 0.0
    status: str = "complete"
    error: Optional[str] = None


class Pipeline:
    """Simple sequential pipeline: plan → code → sandbox → audit."""

    def __init__(self, registry: Optional[GemRegistry] = None):
        self.registry = registry or build_default_registry()
        self.orchestrator = Orchestrator()

    def run(self, objective: str, prefer_local: bool = True) -> PipelineResult:
        task_id = uuid4()
        state = self.orchestrator.start(task_id)
        result = PipelineResult(task_id=task_id, objective=objective)

        try:
            # 1. PLAN
            plan_req = Envelope(
                task_id=task_id,
                target_gem="selenite",
                payload=SeleniteRequest(user_query=objective),
            )
            plan_res = self.registry.execute(plan_req)
            state = self.orchestrator.process_response(plan_req, plan_res)

            if plan_res.error or not isinstance(plan_res.payload, SeleniteResponse):
                result.status = "error"
                result.error = plan_res.error.message if plan_res.error else "Planning failed"
                return result

            result.plan = plan_res.payload.plan

            # 2. CODE (use Rose Quartz)
            code_prompt = (
                f"Write Python code for this objective:\n{objective}\n\n"
                f"Plan:\n{result.plan.model_dump_json(indent=2)}\n\n"
                "Return only the code, no markdown."
            )
            code_req = Envelope(
                task_id=task_id,
                target_gem="rose-quartz",
                payload=RoseQuartzRequest(
                    messages=[ChatMessage(role="user", content=code_prompt)],
                    prefer_local=True,
                ),
            )
            code_res = self.registry.execute(code_req)
            state = self.orchestrator.process_response(code_req, code_res)

            if code_res.error or not isinstance(code_res.payload, RoseQuartzResponse):
                result.status = "error"
                result.error = code_res.error.message if code_res.error else "Code generation failed"
                return result

            generated = code_res.payload.content.strip()
            # Strip markdown fences if present
            if generated.startswith("```"):
                lines = generated.split("\n")
                lines = lines[1:]  # drop ```python
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                generated = "\n".join(lines)

            result.generated_code = generated

            # 3. SANDBOX
            sand_req = Envelope(
                task_id=task_id,
                target_gem="clear-quartz",
                payload=ClearQuartzRequest(code=generated, language="python"),
            )
            sand_res = self.registry.execute(sand_req)
            state = self.orchestrator.process_response(sand_req, sand_res)

            if sand_res.error or not isinstance(sand_res.payload, ClearQuartzResponse):
                result.status = "error"
                result.error = sand_res.error.message if sand_res.error else "Sandbox failed"
                return result

            result.sandbox = sand_res.payload
            result.confidence = compute_clear_quartz_confidence(sand_res.payload)

            # 4. AUDIT
            audit_req = Envelope(
                task_id=task_id,
                target_gem="black-tourmaline",
                payload=BlackTourmalineRequest(artifact=generated, artifact_type="code"),
            )
            audit_res = self.registry.execute(audit_req)
            # Don't fail the whole pipeline on audit errors for now
            if not audit_res.error and isinstance(audit_res.payload, BlackTourmalineResponse):
                result.audit = audit_res.payload
                if not audit_res.payload.approved:
                    result.confidence = min(result.confidence, 0.3)

            result.status = "complete"
            return result

        except Exception as e:
            return PipelineResult(
                task_id=task_id if "task_id" in dir() else uuid4(),
                objective=objective if "objective" in dir() else "",
                status="error",
                error=str(e),
            )


# Fix forward refs used in pipeline result
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from core.schemas import ExecutionPlan, ClearQuartzResponse, BlackTourmalineResponse


class PipelineResult(BaseModel):
    task_id: UUID
    objective: str
    plan: Optional[ExecutionPlan] = None
    generated_code: Optional[str] = None
    sandbox: Optional[ClearQuartzResponse] = None
    audit: Optional[BlackTourmalineResponse] = None
    confidence: float = 0.0
    status: str = "complete"
    error: Optional[str] = None
