"""Legacy verify/audit/reward spine peeled off Pipeline._verify_legacy."""
from __future__ import annotations

import time
from typing import Any, List, Optional, Tuple

from core.learning import compute_reward
from core.loop.gems_call import audit_execute
from core.loop.stage_mark import skip_detail
from core.progress import write_progress
from core.schemas import (
    BlackTourmalineResponse,
    Envelope,
    LabradoriteRequest,
    LabradoriteResponse,
)

def verify_legacy(
    registry: Any,
    result: Any,
    *,
    objective: str,
    generated: str,
    critique: bool,
    holdout_test: str,
    sent_prompts: List[str],
    tool_assist: bool,
    skip: Optional[set] = None,
) -> Tuple[Optional[int], int, str]:
    """Pre-refactor inline spine (default path); removed when
    ETHER_LOOP_RUNNER becomes the only path. Byte-identical behavior to
    the pre-refactor inline block (legacy pipeline.py:649-841). Returns
    (exit_code, total_tests, effective holdout_test); everything else
    mutates `result` exactly as the inline block did."""
    from core.pipeline import StageResult

    skip = skip or set()
    task_id = result.task_id
    tid = str(task_id)
    if tool_assist and generated:
        t_sc = time.perf_counter()
        write_progress(tid, objective, "tool_scan")
        try:
            from gems.grandidierite.registry import run_tool

            scan = run_tool("secret_scan", {"text": generated})
            sub = run_tool("subprocess_audit", {"text": generated})
            scan_ok = bool(scan.get("ok") and (scan.get("result") or {}).get("clean", True))
            risky = bool((sub.get("result") or {}).get("risky"))
            if not scan_ok or risky:
                result.confidence = min(result.confidence, 0.25)
            result.stages.append(
                StageResult(
                    stage="tool_scan",
                    success=scan_ok and not risky,
                    detail=f"secrets_clean={scan_ok} risky_exec={risky}",
                    duration_ms=(time.perf_counter() - t_sc) * 1000,
                )
            )
        except Exception as e:
            result.stages.append(
                StageResult(
                    stage="tool_scan",
                    success=False,
                    detail=str(e)[:120],
                    duration_ms=(time.perf_counter() - t_sc) * 1000,
                )
            )

    t4 = time.perf_counter()
    write_progress(tid, objective, "audit", detail=skip_detail(skip or set(), "audit"))
    audit_req, audit_res = audit_execute(
        registry, task_id=task_id, generated=generated
    )
    if not audit_res.error and isinstance(audit_res.payload, BlackTourmalineResponse):
        result.audit = audit_res.payload
        if not audit_res.payload.approved:
            result.confidence = min(result.confidence, 0.3)
        result.stages.append(
            StageResult(
                stage="audit",
                success=audit_res.payload.approved,
                detail=f"risk={audit_res.payload.risk_score}",
                duration_ms=(time.perf_counter() - t4) * 1000,
            )
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
        result.confidence = min(result.confidence, 0.3)
        result.stages.append(
            StageResult(
                stage="audit",
                success=False,
                detail=f"audit unavailable: {str(audit_err)[:160]}",
                duration_ms=(time.perf_counter() - t4) * 1000,
            )
        )

    if critique:
        t5 = time.perf_counter()
        crit_req = Envelope(
            task_id=task_id,
            target_gem="labradorite",
            payload=LabradoriteRequest(code=generated),
        )
        crit_res = registry.execute(crit_req)
        if not crit_res.error and isinstance(crit_res.payload, LabradoriteResponse):
            result.critique = crit_res.payload
            result.stages.append(
                StageResult(
                    stage="critique",
                    success=True,
                    detail=crit_res.payload.critique[:80],
                    duration_ms=(time.perf_counter() - t5) * 1000,
                )
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
            result.stages.append(
                StageResult(
                    stage="critique",
                    success=False,
                    detail=f"critique unavailable: {str(crit_err)[:160]}",
                    duration_ms=(time.perf_counter() - t5) * 1000,
                )
            )

    exit_code = result.sandbox.exit_code if result.sandbox else None
    # An audit-gem outage is not a rejection. compute_reward turns
    # audit_approved=False into a flat -0.2, so folding "the auditor was
    # down" into the same flag trained the bandit to punish strategies
    # whose code the auditor never even looked at. When no verdict
    # exists we stay neutral here; the already-clamped confidence (0.3)
    # keeps the reward from being inflated, and _log still records
    # audit_approved=False so the flywheel gate keeps failing closed.
    audit_ok = bool(result.audit.approved) if result.audit is not None else True
    had_self = bool(result.sandbox and result.sandbox.total_tests > 0)
    total_tests = int(result.sandbox.total_tests) if result.sandbox else 0

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

            guard = _guard_check("\n\n".join(sent_prompts), holdout_test)
        except Exception as e:  # never let the guard break a run
            guard = {"clean": True, "leak_count": 0, "detail": f"guard error: {e}"}

        if not guard.get("clean"):
            result.stages.append(
                StageResult(
                    stage="prompt_guard",
                    success=False,
                    detail=f"LEAK: {guard.get('detail', '')}"[:300],
                )
            )
            result.holdout_ok = None
            result.stages.append(
                StageResult(
                    stage="holdout",
                    success=False,
                    detail="not graded — holdout leaked into the prompt",
                )
            )
            holdout_test = ""  # skip grading; the result would be meaningless

    if holdout_test.strip():
        try:
            from core.holdout import grade_against_holdout

            verdict = grade_against_holdout(result.generated_code or "", holdout_test)
            holdout_ok = bool(verdict.get("ok"))
            result.stages.append(
                StageResult(
                    stage="holdout",
                    success=holdout_ok,
                    detail=(
                        f"{verdict.get('asserts') or 0} unseen asserts"
                        + ("" if holdout_ok else f" — {verdict.get('reason') or ''}")
                    ),
                )
            )
        except Exception as e:
            holdout_ok = False
            result.stages.append(
                StageResult(
                    stage="holdout",
                    success=False,
                    detail=f"holdout grading failed: {str(e)[:160]}",
                )
            )
    result.holdout_ok = holdout_ok

    result.reward = compute_reward(
        exit_code=exit_code,
        confidence=result.confidence,
        audit_approved=audit_ok,
        retries=result.retries,
        verification_score=result.verification_score,
        had_self_check=had_self,
        plan_ok=result.plan_ok,
        first_compile_ok=result.first_compile_ok,
        used_burst=result.used_burst,
        holdout_ok=holdout_ok,
    )
    return exit_code, total_tests, holdout_test
