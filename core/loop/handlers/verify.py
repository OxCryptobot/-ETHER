"""Verify handler — the extracted verification spine of Pipeline.run (legacy lines 649-841).

Strangler-fig stage 2: when ETHER_LOOP_RUNNER=1, Pipeline.run routes the
verification spine (tool_scan → audit → critique → gate inputs → prompt_guard
→ holdout → reward) through VerificationHandler instead of the inline legacy
block (`Pipeline._verify_legacy`). Behavior is byte-identical by construction;
scripts/shadow_runner.py proves it scenario by scenario.

Boundary rules (topology D2): stdlib, pydantic, core.schemas, core.learning,
core.progress only, plus the same lazy core.prompt_guard / core.holdout
lookups the legacy block used (kept inline so both paths resolve the same
patch point). No gems.* imports — the grandidierite bridge is injected as
`run_tool`. Never imports core.pipeline: stages leave here as
StageResult-shaped dicts and the caller constructs them.
"""

from __future__ import annotations

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

    task_id: str  # str(result.task_id)
    objective: str
    generated: str  # generated or ""
    tool_assist: bool
    critique: bool
    holdout_test: str
    sent_prompts: List[str]  # every prompt actually sent, for the leak guard
    has_sandbox: bool  # result.sandbox is not None
    sandbox_exit: Optional[int]  # result.sandbox.exit_code if result.sandbox else None
    sandbox_total_tests: int  # int(result.sandbox.total_tests) if result.sandbox else 0
    confidence: float  # current result.confidence (post-sandbox scores)
    verification_score: float
    retries: int
    plan_ok: bool
    first_compile_ok: bool
    used_burst: bool


class VerificationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stages: List[Dict[str, Any]]  # StageResult-shaped dicts, legacy order/content
    confidence: float  # post-clamps
    audit: Optional[Dict[str, Any]]  # BlackTourmalineResponse.model_dump() or None
    critique: Optional[Dict[str, Any]]  # LabradoriteResponse.model_dump() or None
    holdout_ok: Optional[bool]
    holdout_test: str  # effective ("" after a leak)
    reward: float
    exit_code: Optional[int]
    total_tests: int


class VerificationHandler:
    """Runs the verification spine against injected boundaries."""

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
            # A gem outage used to produce no StageResult at all: the audit
            # row simply vanished, so an unaudited run was indistinguishable
            # from an approved one. Record the failure explicitly and clamp
            # confidence exactly as an un-approved audit would — code nobody
            # audited must not score as if it had been.
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

        if ctx.critique:
            t5 = time.perf_counter()
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
            else:
                # Same silent-vanish bug as audit: --critique was requested,
                # so the absence of a critique row has to be reported rather
                # than read as "critique was skipped".
                crit_err = (
                    crit_res.error.message
                    if crit_res.error
                    else f"critique returned {type(crit_res.payload).__name__}, expected LabradoriteResponse"
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
        # An audit-gem outage is not a rejection. compute_reward turns
        # audit_approved=False into a flat -0.2, so folding "the auditor was
        # down" into the same flag trained the bandit to punish strategies
        # whose code the auditor never even looked at. When no verdict
        # exists we stay neutral here; the already-clamped confidence (0.3)
        # keeps the reward from being inflated, and _log still records
        # audit_approved=False so the flywheel gate keeps failing closed.
        audit_ok = bool(audit_payload.approved) if audit_payload is not None else True
        had_self = bool(ctx.has_sandbox and ctx.sandbox_total_tests > 0)
        total_tests = ctx.sandbox_total_tests

        # Grade against assertions the generator never saw, before the
        # reward is computed, so the learning signal is not purely
        # self-graded. Fails closed: a grading error is not a pass.
        holdout_ok: Optional[bool] = None
        if holdout_test.strip():
            # If the holdout reached the prompt, the verdict is worthless —
            # the model was shown the answer. Report it and refuse to grade
            # rather than banking an unearned pass. BM25 retrieval leaked
            # assertions into 12 of 15 bench prompts this way, which is how
            # a pass_rate of 0.933 came to be reported as honest.
            try:
                from core.prompt_guard import check as _guard_check

                guard = _guard_check("\n\n".join(ctx.sent_prompts), holdout_test)
            except Exception as e:  # never let the guard break a run
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
                holdout_test = ""  # skip grading; the result would be meaningless

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
