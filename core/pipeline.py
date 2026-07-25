"""End-to-end pipeline for @ETHER.

Flow:
  plan (Selenite) → code (Rose Quartz) → sandbox (Clear Quartz) → audit (Black Tourmaline)
  + automatic Amethyst logging
"""

from __future__ import annotations

from uuid import uuid4, UUID
from typing import Optional, List
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from core.schemas import (
    Envelope,
    SeleniteRequest,
    SeleniteResponse,
    RoseQuartzRequest,
    RoseQuartzResponse,
    ClearQuartzRequest,
    ClearQuartzResponse,
    BlackTourmalineRequest,
    BlackTourmalineResponse,
    AmethystRequest,
    ChatMessage,
    ExecutionPlan,
)
from core.registry import GemRegistry, build_default_registry
from core.orchestrator import Orchestrator
from core.confidence import compute_clear_quartz_confidence


class StageResult(BaseModel):
    stage: str
    success: bool
    detail: str = ""
    duration_ms: float = 0.0


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
    stages: List[StageResult] = Field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""


class Pipeline:
    """Sequential pipeline: plan → code → sandbox → audit + log."""

    def __init__(self, registry: Optional[GemRegistry] = None):
        self.registry = registry or build_default_registry()
        self.orchestrator = Orchestrator()

    def run(self, objective: str, prefer_local: bool = True) -> PipelineResult:
        task_id = uuid4()
        self.orchestrator.start(task_id)
        started = datetime.now(timezone.utc).isoformat()
        result = PipelineResult(task_id=task_id, objective=objective, started_at=started)

        try:
            # 1. PLAN
            plan_req = Envelope(
                task_id=task_id,
                target_gem="selenite",
                payload=SeleniteRequest(user_query=objective),
            )
            plan_res = self.registry.execute(plan_req)
            self.orchestrator.process_response(plan_req, plan_res)

            if plan_res.error or not isinstance(plan_res.payload, SeleniteResponse):
                msg = plan_res.error.message if plan_res.error else "Planning failed"
                result.stages.append(StageResult(stage="plan", success=False, detail=msg))
                result.status = "error"
                result.error = msg
                self._log(result)
                return result

            result.plan = plan_res.payload.plan
            result.stages.append(StageResult(stage="plan", success=True, detail=f"{len(result.plan.steps)} steps"))

            # 2. CODE
            code_prompt = (
                f"Write Python code for this objective:\n{objective}\n\n"
                f"Plan:\n{result.plan.model_dump_json(indent=2)}\n\n"
                "Return only the code. No markdown fences. No explanation."
            )
            code_req = Envelope(
                task_id=task_id,
                target_gem="rose-quartz",
                payload=RoseQuartzRequest(
                    messages=[ChatMessage(role="user", content=code_prompt)],
                    prefer_local=prefer_local,
                ),
            )
            code_res = self.registry.execute(code_req)
            self.orchestrator.process_response(code_req, code_res)

            if code_res.error or not isinstance(code_res.payload, RoseQuartzResponse):
                msg = code_res.error.message if code_res.error else "Code generation failed"
                result.stages.append(StageResult(stage="code", success=False, detail=msg))
                result.status = "error"
                result.error = msg
                self._log(result)
                return result

            generated = self._strip_fences(code_res.payload.content)
            result.generated_code = generated
            result.stages.append(StageResult(stage="code", success=True, detail=f"{len(generated)} chars"))

            # 3. SANDBOX
            sand_req = Envelope(
                task_id=task_id,
                target_gem="clear-quartz",
                payload=ClearQuartzRequest(code=generated, language="python"),
            )
            sand_res = self.registry.execute(sand_req)
            self.orchestrator.process_response(sand_req, sand_res)

            if sand_res.error or not isinstance(sand_res.payload, ClearQuartzResponse):
                msg = sand_res.error.message if sand_res.error else "Sandbox failed"
                result.stages.append(StageResult(stage="sandbox", success=False, detail=msg))
                result.status = "error"
                result.error = msg
                self._log(result)
                return result

            result.sandbox = sand_res.payload
            result.confidence = compute_clear_quartz_confidence(sand_res.payload)
            result.stages.append(
                StageResult(
                    stage="sandbox",
                    success=sand_res.payload.exit_code == 0,
                    detail=f"exit={sand_res.payload.exit_code} time={sand_res.payload.execution_time}s",
                )
            )

            # 4. AUDIT
            audit_req = Envelope(
                task_id=task_id,
                target_gem="black-tourmaline",
                payload=BlackTourmalineRequest(artifact=generated, artifact_type="code"),
            )
            audit_res = self.registry.execute(audit_req)

            if not audit_res.error and isinstance(audit_res.payload, BlackTourmalineResponse):
                result.audit = audit_res.payload
                if not audit_res.payload.approved:
                    result.confidence = min(result.confidence, 0.3)
                result.stages.append(
                    StageResult(
                        stage="audit",
                        success=audit_res.payload.approved,
                        detail=f"risk={audit_res.payload.risk_score}",
                    )
                )
            else:
                result.stages.append(StageResult(stage="audit", success=False, detail="audit skipped/failed"))

            result.status = "complete"
            result.finished_at = datetime.now(timezone.utc).isoformat()
            self._log(result)
            return result

        except Exception as e:
            result.status = "error"
            result.error = str(e)
            result.finished_at = datetime.now(timezone.utc).isoformat()
            result.stages.append(StageResult(stage="exception", success=False, detail=str(e)))
            self._log(result)
            return result

    def _strip_fences(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines)
        return text

    def _log(self, result: PipelineResult) -> None:
        """Best-effort Amethyst logging. Never raises."""
        try:
            log_req = Envelope(
                task_id=result.task_id,
                target_gem="amethyst",
                payload=AmethystRequest(
                    action="log",
                    interaction={
                        "task_id": str(result.task_id),
                        "objective": result.objective,
                        "status": result.status,
                        "confidence": result.confidence,
                        "error": result.error,
                        "stages": [s.model_dump() for s in result.stages],
                    },
                ),
            )
            self.registry.execute(log_req)
        except Exception:
            pass
