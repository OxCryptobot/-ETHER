"""End-to-end pipeline for @ETHER."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from uuid import uuid4, UUID

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
    LabradoriteRequest,
    LabradoriteResponse,
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


class PipelineResult(BaseModel):
    task_id: UUID
    objective: str
    plan: Optional[ExecutionPlan] = None
    generated_code: Optional[str] = None
    sandbox: Optional[ClearQuartzResponse] = None
    audit: Optional[BlackTourmalineResponse] = None
    critique: Optional[LabradoriteResponse] = None
    confidence: float = 0.0
    status: str = "complete"
    error: Optional[str] = None
    stages: List[StageResult] = Field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""


class Pipeline:
    def __init__(self, registry: Optional[GemRegistry] = None):
        self.registry = registry or build_default_registry()
        self.orchestrator = Orchestrator()
        self.runs_dir = Path("memory/runs")
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run(self, objective: str, prefer_local: bool = True, critique: bool = False) -> PipelineResult:
        task_id = uuid4()
        self.orchestrator.start(task_id)
        result = PipelineResult(
            task_id=task_id,
            objective=objective,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        timeout = int(os.getenv("ETHER_SANDBOX_TIMEOUT", "60"))

        try:
            # PLAN
            plan_req = Envelope(task_id=task_id, target_gem="selenite", payload=SeleniteRequest(user_query=objective))
            plan_res = self.registry.execute(plan_req)
            self.orchestrator.process_response(plan_req, plan_res)
            if plan_res.error or not isinstance(plan_res.payload, SeleniteResponse):
                return self._fail(result, "plan", plan_res.error.message if plan_res.error else "plan failed")
            result.plan = plan_res.payload.plan
            result.stages.append(StageResult(stage="plan", success=True, detail=f"{len(result.plan.steps)} steps"))

            # CODE
            prompt = f"Write Python code for:\n{objective}\n\nPlan:\n{result.plan.model_dump_json(indent=2)}\n\nReturn only code, no markdown."
            code_req = Envelope(
                task_id=task_id,
                target_gem="rose-quartz",
                payload=RoseQuartzRequest(messages=[ChatMessage(role="user", content=prompt)], prefer_local=prefer_local),
            )
            code_res = self.registry.execute(code_req)
            self.orchestrator.process_response(code_req, code_res)
            if code_res.error or not isinstance(code_res.payload, RoseQuartzResponse):
                return self._fail(result, "code", code_res.error.message if code_res.error else "code failed")
            generated = self._strip(code_res.payload.content)
            result.generated_code = generated
            result.stages.append(StageResult(stage="code", success=True, detail=f"{len(generated)} chars"))

            # SANDBOX
            sand_req = Envelope(
                task_id=task_id,
                target_gem="clear-quartz",
                payload=ClearQuartzRequest(code=generated),
                timeout_seconds=timeout,
            )
            sand_res = self.registry.execute(sand_req)
            self.orchestrator.process_response(sand_req, sand_res)
            if sand_res.error or not isinstance(sand_res.payload, ClearQuartzResponse):
                return self._fail(result, "sandbox", sand_res.error.message if sand_res.error else "sandbox failed")
            result.sandbox = sand_res.payload
            result.confidence = compute_clear_quartz_confidence(sand_res.payload)
            result.stages.append(StageResult(stage="sandbox", success=sand_res.payload.exit_code == 0, detail=f"exit={sand_res.payload.exit_code}"))

            # AUDIT
            audit_req = Envelope(
                task_id=task_id,
                target_gem="black-tourmaline",
                payload=BlackTourmalineRequest(artifact=generated),
            )
            audit_res = self.registry.execute(audit_req)
            if not audit_res.error and isinstance(audit_res.payload, BlackTourmalineResponse):
                result.audit = audit_res.payload
                if not audit_res.payload.approved:
                    result.confidence = min(result.confidence, 0.3)
                result.stages.append(StageResult(stage="audit", success=audit_res.payload.approved, detail=f"risk={audit_res.payload.risk_score}"))

            # OPTIONAL CRITIQUE
            if critique:
                crit_req = Envelope(
                    task_id=task_id,
                    target_gem="labradorite",
                    payload=LabradoriteRequest(code=generated),
                )
                crit_res = self.registry.execute(crit_req)
                if not crit_res.error and isinstance(crit_res.payload, LabradoriteResponse):
                    result.critique = crit_res.payload
                    result.stages.append(StageResult(stage="critique", success=True, detail=crit_res.payload.critique[:80]))

            result.status = "complete"
            result.finished_at = datetime.now(timezone.utc).isoformat()
            self._persist(result)
            self._log(result)
            return result

        except Exception as e:
            return self._fail(result, "exception", str(e))

    def _fail(self, result: PipelineResult, stage: str, msg: str) -> PipelineResult:
        result.status = "error"
        result.error = msg
        result.stages.append(StageResult(stage=stage, success=False, detail=msg))
        result.finished_at = datetime.now(timezone.utc).isoformat()
        self._persist(result)
        self._log(result)
        return result

    def _strip(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines)
        return text

    def _persist(self, result: PipelineResult) -> None:
        try:
            path = self.runs_dir / f"{result.task_id}.json"
            path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        except Exception:
            pass

    def _log(self, result: PipelineResult) -> None:
        try:
            self.registry.execute(
                Envelope(
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
                        },
                    ),
                )
            )
        except Exception:
            pass
