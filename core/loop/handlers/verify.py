"""Verify handler — verification spine with mandatory Labradorite critique.

Infinity topology: critique is essential (not gated on --critique). Reviews
flow to the shared memory bus so the next Selenite plan can self-tune.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from core.learning import compute_reward
from core.progress import write_progress
from core.schemas import (
    BlackTourmalineRequest,
    BlackTourmalineResponse,
    Envelope,
    LabradoriteRequest,
    LabradoriteResponse,
)


class VerificationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    objective: str
    generated: str
    tool_assist: bool
    critique: bool  # retained for API compat; ignored — critique is always on
    holdout_test: str
    sent_prompts: List[str]
    has_sandbox: bool
    sandbox_exit: Optional[int]
    sandbox_total_tests: int
    confidence: float
    verification_score: float
    retries: int
    plan_ok: bool
    first_compile_ok: bool
    used_burst: bool


class VerificationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stages: List[Dict[str, Any]]
    confidence: float
    audit: Optional[Dict[str, Any]]
    critique: Optional[Dict[str, Any]]
    holdout_ok: Optional[bool]
    holdout_test: str
    reward: float
    exit_code: Optional[int]
    total_tests: int


class VerificationHandler:
    def __init__(self, registry: Any, run_tool: Callable[..., Dict[str, Any]]):
        self._registry = registry
        self._run_tool = run_tool

    def run(self, ctx: VerificationContext) -> VerificationOutcome:
        task_id = UUID(ctx.task_id)
        tid = ctx.task_id
        generated = ctx.generated
        holdout_test = ctx.holdout_test
        confidence = ctx.confidence
        stages: List[Dict[str, Any]] = []
        audit_payload: Optional[BlackTourmalineResponse] = None
        critique_payload: Optional[LabradoriteResponse] = None

        if ctx.tool_assist and generated:
            t_sc = time.perf_counter()
            write_progress(tid, ctx.objective, "tool_scan")
            try:
                scan = self._run_tool("secret_scan", {"text": generated})
                sub = self._run_tool("subprocess_audit", {"text": generated})
                scan_ok = bool(scan.get("ok") and (scan.get("result") or {}).get("clean", True))
                risky = bool((sub.get("result") or {}).get("risky"))
                if not scan_ok or risky:
                    confidence = min(confidence, 0.25)
                stages.append(
                    {
                        "stage": "tool_scan",
                        "success": scan_ok and not risky,
                        "detail": f"secrets_clean={scan_ok} risky_exec={risky}",
                        "duration_ms": (time.perf_counter() - t_sc) * 1000,
                    }
                )
            except Exception as e:
                stages.append(
                    {
                        "stage": "tool_scan",
                        "success": False,
                        "detail": str(e)[:120],
                        "duration_ms": (time.perf_counter() - t_sc) * 1000,
                    }
                )

        t4 = time.perf_counter()
        write_progress(tid, ctx.objective, "audit")
        audit_req = Envelope(
            task_id=task_id,
            target_gem="black-tourmaline",
            payload=BlackTourmalineRequest(artifact=generated),
        )
        audit_res = self._registry.execute(audit_req)
        if not audit_res.error and isinstance(audit_res.payload, BlackTourmalineResponse):
            audit_payload = audit_res.payload
            if not audit_res.payload.approved:
                confidence = min(confidence, 0.3)
            stages.append(
                {
                    "stage": "audit",
                    "success": audit_res.payload.approved,
                    "detail": f"risk={audit_res.payload.risk_score}",
                    "duration_ms": (time.perf_counter() - t4) * 1000,
                }
            )
        else:
            audit_err = (
                audit_res.error.message
                if audit_res.error
                else f"audit returned {type(audit_res.payload).__name__}, expected BlackTourmalineResponse"
            )
            confidence = min(confidence, 0.3)
            stages.append(
                {
                    "stage": "audit",
                    "success": False,
                    "detail": f"audit unavailable: {str(audit_err)[:160]}",
                    "duration_ms": (time.perf_counter() - t4) * 1000,
                }
            )

        # Infinity loop: Labradorite is always-on (ETHER_SKIP_CRITIQUE=1 to disable in tests)
        skip_crit = os.getenv("ETHER_SKIP_CRITIQUE", "0") == "1"
        if not skip_crit and generated:
            t5 = time.perf_counter()
            write_progress(tid, ctx.objective, "critique")
            crit_req = Envelope(
                task_id=task_id,
                target_gem="labradorite",
                payload=LabradoriteRequest(code=generated),
            )
            crit_res = self._registry.execute(crit_req)
            if not crit_res.error and isinstance(crit_res.payload, LabradoriteResponse):
                critique_payload = crit_res.payload
                stages.append(
                    {
                        "stage": "critique",
                        "success": True,
                        "detail": crit_res.payload.critique[:80],
                        "duration_ms": (time.perf_counter() - t5) * 1000,
                    }
                )
                try:
                    from core.memory_bus import record_critique

                    record_critique(
                        objective=ctx.objective,
                        code=generated,
                        critique=crit_res.payload.critique,
                        suggestions=list(crit_res.payload.suggested_improvements or []),
                        complexity_score=float(crit_res.payload.complexity_score or 0),
                        success=(ctx.sandbox_exit == 0),
                        confidence=confidence,
                        task_id=tid,
                    )
                except Exception as e:
                    stages.append(
                        {
                            "stage": "memory_bus",
                            "success": False,
                            "detail": f"critique bus: {type(e).__name__}",
                        }
                    )
            else:
                crit_err = (
                    crit_res.error.message
                    if crit_res.error
                    else f"critique returned {type(crit_res.payload).__name__}"
                )
                stages.append(
                    {
                        "stage": "critique",
                        "success": False,
                        "detail": f"critique unavailable: {str(crit_err)[:160]}",
                        "duration_ms": (time.perf_counter() - t5) * 1000,
                    }
                )

        exit_code = ctx.sandbox_exit
        audit_ok = bool(audit_payload.approved) if audit_payload is not None else True
        had_self = bool(ctx.has_sandbox and ctx.sandbox_total_tests > 0)
        total_tests = ctx.sandbox_total_tests

        holdout_ok: Optional[bool] = None
        if holdout_test.strip():
            try:
                from core.prompt_guard import check as _guard_check

                guard = _guard_check("\n\n".join(ctx.sent_prompts), holdout_test)
            except Exception as e:
                guard = {"clean": True, "leak_count": 0, "detail": f"guard error: {e}"}

            if not guard.get("clean"):
                stages.append(
                    {
                        "stage": "prompt_guard",
                        "success": False,
                        "detail": f"LEAK: {guard.get('detail', '')}"[:300],
                    }
                )
                holdout_ok = None
                stages.append(
                    {
                        "stage": "holdout",
                        "success": False,
                        "detail": "not graded — holdout leaked into the prompt",
                    }
                )
                holdout_test = ""

        if holdout_test.strip():
            try:
                from core.holdout import grade_against_holdout

                verdict = grade_against_holdout(generated or "", holdout_test)
                holdout_ok = bool(verdict.get("ok"))
                stages.append(
                    {
                        "stage": "holdout",
                        "success": holdout_ok,
                        "detail": (
                            f"{verdict.get('asserts') or 0} unseen asserts"
                            + ("" if holdout_ok else f" — {verdict.get('reason') or ''}")
                        ),
                    }
                )
            except Exception as e:
                holdout_ok = False
                stages.append(
                    {
                        "stage": "holdout",
                        "success": False,
                        "detail": f"holdout grading failed: {str(e)[:160]}",
                    }
                )

        reward = compute_reward(
            exit_code=exit_code,
            confidence=confidence,
            audit_approved=audit_ok,
            retries=ctx.retries,
            verification_score=ctx.verification_score,
            had_self_check=had_self,
            plan_ok=ctx.plan_ok,
            first_compile_ok=ctx.first_compile_ok,
            used_burst=ctx.used_burst,
            holdout_ok=holdout_ok,
        )

        return VerificationOutcome(
            stages=stages,
            confidence=confidence,
            audit=audit_payload.model_dump(mode="json") if audit_payload is not None else None,
            critique=(
                critique_payload.model_dump(mode="json") if critique_payload is not None else None
            ),
            holdout_ok=holdout_ok,
            holdout_test=holdout_test,
            reward=reward,
            exit_code=exit_code,
            total_tests=total_tests,
        )
