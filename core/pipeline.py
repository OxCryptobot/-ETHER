"""End-to-end pipeline: experience, process rewards, burst-on-retry, multifile assist."""

from __future__ import annotations

import inspect
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List
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
    GrandidieriteRequest,
    ChatMessage,
    ExecutionPlan,
)
from core.registry import GemRegistry, build_default_registry
from core.orchestrator import Orchestrator
from core.confidence import compute_scores
from core.context import gather_workspace_context, context_enabled
from core.learning import (
    BanditPolicy,
    arm_behaviour,
    compute_reward,
    learning_enabled,
    strategy_prompt_addon,
)
from core.fail_streak import record_outcome, maybe_propose_fabricate
from core.progress import write_progress, clear_progress
from core.repair import repair_prompt, classify_stderr
from core.patterns import index_pass_pattern
from core.experience import retrieve as experience_retrieve, record as experience_record
from core.bench_guardian import is_frozen
from core.pipeline_burst import decide_burst
from core.pipeline_select import current_tier, select_strategy_with_context

MAX_CODE_CHARS = 50_000


@dataclass
class _Attempt:
    """One generation attempt = one bandit decision.

    Each attempt is drawn in its own context (attempt 1 in the generation
    context, a retry in the repair context implied by the observed
    `fail_kind`) and is therefore credited separately. Handing the whole run's
    reward to the arm that produced attempt 1 when attempt 2 used a different
    arm and fixed the code credits the wrong arm.
    """

    strategy: str
    context: Dict[str, Any] = field(default_factory=dict)
    credited: bool = False


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
    critique: Optional[LabradoriteResponse] = None
    # None when the task supplied no holdout; True/False once graded against
    # assertions the generator never saw.
    holdout_ok: Optional[bool] = None
    confidence: float = 0.0
    execution_score: float = 0.0
    verification_score: float = 0.0
    status: str = "complete"
    error: Optional[str] = None
    stages: List[StageResult] = Field(default_factory=list)
    retries: int = 0
    context_chars: int = 0
    # The arm that produced the code that was finally graded. A retry can pick
    # a different arm, and this reports the one that actually ran.
    strategy: str = "default"
    # One entry per attempt, in order, so the retry decision stays auditable.
    strategies: List[str] = Field(default_factory=list)
    reward: float = 0.0
    few_shot_chars: int = 0
    tool_output_chars: int = 0
    experience_chars: int = 0
    used_burst: bool = False
    first_compile_ok: bool = False
    plan_ok: bool = False
    started_at: str = ""
    finished_at: str = ""


def _is_burst_model(model_used: str) -> bool:
    """Did this response come from the cloud burst model?

    Was `"llama" in model_used or "grok" in ... or "burst" in ...`, which
    marked every run on a local llama-family model as a burst and charged it
    the -0.05 burst penalty in compute_reward. The burst path in
    gems/rose_quartz/router.py labels its responses with ETHER_BURST_MODEL
    (default grok-3) or the literal "burst", so match those exactly.
    """
    m = (model_used or "").strip().lower()
    if not m:
        return False
    configured = (os.getenv("ETHER_BURST_MODEL") or "grok-3").strip().lower()
    return m in {configured, "burst"}


def _looks_multifile(objective: str) -> bool:
    o = objective.lower()
    return bool(
        re.search(r"\b(class|module|package|refactor|file|project|codebase|multi[- ]?file)\b", o)
        or ".py" in o
    )


# Anchored on the repo root, not the CWD. `Path("memory/runs")` meant that
# running `ether run` from any other directory silently wrote the run record
# somewhere else, so it never reached the dashboard, ledger or history — while
# core/progress.py and dashboard/collector.py both anchor on the repo root.
# Module-level so tests can redirect it instead of writing mock runs into the
# real history (61% of it was test artifacts).
ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "memory" / "runs"


class Pipeline:
    def __init__(self, registry: Optional[GemRegistry] = None):
        self.registry = registry or build_default_registry()
        self.orchestrator = Orchestrator()
        self.runs_dir = RUNS_DIR
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.policy = BanditPolicy()

    def run(
        self,
        objective: str,
        prefer_local: bool = True,
        critique: bool = False,
        holdout_test: str = "",
    ) -> PipelineResult:
        """Run the full pipeline.

        `holdout_test` carries assertions the generator never sees. It is
        graded after the sandbox stage and folded into the learning reward, so
        the bandit optimises against independent evidence rather than against
        assertions the model wrote about its own output. It is never added to
        the prompt.
        """
        task_id = uuid4()
        tid = str(task_id)
        # Captured before any work so the `exception` stage in _fail() records
        # the real elapsed time. Passing time.perf_counter() at the call site
        # measured the interval from "now" to "now" and always logged ~0ms.
        run_started = time.perf_counter()
        self.orchestrator.start(task_id)
        result = PipelineResult(
            task_id=task_id,
            objective=objective,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        timeout = int(os.getenv("ETHER_SANDBOX_TIMEOUT", "120"))
        allow_retry = os.getenv("ETHER_SANDBOX_RETRY", "1") == "1"
        tool_assist = os.getenv("ETHER_TOOL_ASSIST", "1") == "1"

        # select_strategy_with_context builds the bandit context (multifile /
        # tier / fail_kind) and passes it to BanditPolicy.select. Calling
        # self.policy.select() bare left every contextual feature permanently
        # unset, so the contextual bandit degraded to a plain epsilon-greedy one.
        # The context comes back so the reward can be credited to the arm *in
        # the situation it was drawn from*.
        strategy, strategy_ctx = select_strategy_with_context(objective, self.policy)
        attempts: List[_Attempt] = [_Attempt(strategy=strategy, context=strategy_ctx)]
        result.strategy = strategy
        result.strategies = [strategy]
        write_progress(tid, objective, "start", strategy=strategy)

        tool_block = ""
        last_err = ""
        fail_kind = ""

        try:
            t0 = time.perf_counter()
            available = []
            try:
                from gems.grandidierite.registry import list_tools

                available = [n.replace(".py", "") for n in list_tools().get("persistent", [])]
            except Exception:
                pass

            write_progress(tid, objective, "plan")
            plan_req = Envelope(
                task_id=task_id,
                target_gem="selenite",
                payload=SeleniteRequest(user_query=objective, available_tools=available),
            )
            plan_res = self.registry.execute(plan_req)
            self.orchestrator.process_response(plan_req, plan_res)
            if plan_res.error or not isinstance(plan_res.payload, SeleniteResponse):
                return self._fail(
                    result,
                    "plan",
                    plan_res.error.message if plan_res.error else "plan failed",
                    t0,
                    attempts,
                )
            result.plan = plan_res.payload.plan
            result.plan_ok = True
            result.stages.append(
                StageResult(
                    stage="plan",
                    success=True,
                    detail=f"{len(result.plan.steps)} steps tool={plan_res.payload.needs_tool}",
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )
            )

            if plan_res.payload.needs_tool and plan_res.payload.tool_request:
                t1 = time.perf_counter()
                treq = dict(plan_res.payload.tool_request)
                action = str(treq.get("action") or "generate")
                write_progress(tid, objective, "extend", action)
                if action == "run":
                    try:
                        from gems.grandidierite.registry import run_tool

                        name = str(treq.get("name") or "")
                        payload = treq.get("payload") or {}
                        tr = run_tool(name, payload)
                        tool_block = str(tr)[:2000]
                        result.tool_output_chars = len(tool_block)
                        result.stages.append(
                            StageResult(
                                stage="tool_run",
                                success=bool(tr.get("ok")),
                                detail=name,
                                duration_ms=(time.perf_counter() - t1) * 1000,
                            )
                        )
                    except Exception as e:
                        result.stages.append(
                            StageResult(
                                stage="tool_run",
                                success=False,
                                detail=str(e)[:120],
                                duration_ms=(time.perf_counter() - t1) * 1000,
                            )
                        )
                else:
                    if action in ("generate", "fabricate") and is_frozen():
                        result.stages.append(
                            StageResult(
                                stage="extend",
                                success=False,
                                detail="blocked_by_bench_guardian",
                                duration_ms=(time.perf_counter() - t1) * 1000,
                            )
                        )
                    else:
                        g_req = Envelope(
                            task_id=task_id,
                            target_gem="grandidierite",
                            payload=GrandidieriteRequest(tool_request=treq),
                        )
                        g_res = self.registry.execute(g_req)
                        result.stages.append(
                            StageResult(
                                stage="extend",
                                success=not bool(g_res.error),
                                detail=action,
                                duration_ms=(time.perf_counter() - t1) * 1000,
                            )
                        )

            # Retrieved blocks. few_shot and experience are cheap local lookups
            # done once up front; the workspace context and the repo map are
            # fetched on first use, because whether an arm wants them is part of
            # what the arm *is* — and the arm can change between attempts.
            few_shot = ""
            exp_block = ""
            if tool_assist:
                t_ta = time.perf_counter()
                write_progress(tid, objective, "tool_assist")
                try:
                    from gems.grandidierite.registry import run_tool

                    fs = run_tool("few_shot_pack", {"query": objective, "top_k": 2})
                    if fs.get("ok") and isinstance(fs.get("result"), dict):
                        few_shot = fs["result"].get("block") or ""
                    exp = experience_retrieve(objective, k=3)
                    exp_block = exp.get("block") or ""
                    result.stages.append(
                        StageResult(
                            stage="tool_assist",
                            success=True,
                            detail=f"few_shot={len(few_shot)}c exp={len(exp_block)}c",
                            duration_ms=(time.perf_counter() - t_ta) * 1000,
                        )
                    )
                except Exception as e:
                    result.stages.append(
                        StageResult(
                            stage="tool_assist",
                            success=False,
                            detail=str(e)[:120],
                            duration_ms=(time.perf_counter() - t_ta) * 1000,
                        )
                    )

            lazy: Dict[str, str] = {}

            def repo_map_block() -> str:
                if "repo_map" not in lazy:
                    lazy["repo_map"] = self._fetch_repo_map(result) if tool_assist else ""
                return lazy["repo_map"]

            def workspace_block() -> str:
                if "context" not in lazy:
                    write_progress(tid, objective, "context")
                    lazy["context"] = self._fetch_context(result, objective)
                return lazy["context"]

            generated = ""
            attempt = 0
            max_attempts = 2 if allow_retry else 1
            strategy_hint = strategy_prompt_addon(strategy)

            while attempt < max_attempts:
                attempt += 1
                t2 = time.perf_counter()
                write_progress(tid, objective, "code" if attempt == 1 else "code_retry")

                if attempt > 1:
                    # Re-draw the arm now that a failure class exists. This is
                    # the whole point of the fail_kind feature: at first
                    # selection nothing has failed yet, so the repair branch of
                    # the policy could never fire.
                    strategy, strategy_ctx = select_strategy_with_context(
                        objective, self.policy, fail_kind=fail_kind
                    )
                    attempts.append(_Attempt(strategy=strategy, context=strategy_ctx))
                    result.strategy = strategy
                    result.strategies.append(strategy)
                    strategy_hint = strategy_prompt_addon(strategy)
                behaviour = arm_behaviour(strategy)

                # Which retrieved blocks this arm gets. `no_context` is now a
                # real ablation (it used to still receive the experience block,
                # the few-shot block and the repo map) and `repo_map_on` is now
                # a real addition rather than a sentence of prompt. Resolved
                # before ETHER_FORCE_BURST is set, so a fetch can never leak
                # that variable into the environment.
                exp_txt = exp_block if behaviour.use_experience else ""
                few_shot_txt = few_shot if behaviour.use_few_shot else ""
                repo_map_txt = ""
                if behaviour.force_repo_map or (
                    behaviour.use_workspace_context and _looks_multifile(objective)
                ):
                    repo_map_txt = repo_map_block()
                context_block = workspace_block() if behaviour.use_workspace_context else ""
                # Report what actually reached the model, not what was fetched.
                result.experience_chars = len(exp_txt)
                result.few_shot_chars = len(few_shot_txt)
                result.context_chars = len(context_block)

                # Single policy entry point — no duplicated inline rules
                force_burst = decide_burst(
                    attempt=attempt,
                    strategy=strategy,
                    objective=objective,
                    tier=current_tier(),
                )

                prev_force = os.environ.get("ETHER_FORCE_BURST")
                if force_burst:
                    os.environ["ETHER_FORCE_BURST"] = "1"
                    result.used_burst = True

                try:
                    if attempt == 1:
                        prompt = (
                            f"Write Python code for:\n{objective}\n\n"
                            f"Strategy: {strategy_hint}\n\n"
                            f"Plan:\n{result.plan.model_dump_json(indent=2)}\n\n"
                        )
                        if tool_block:
                            prompt += f"Tool output:\n{tool_block}\n\n"
                        if exp_txt:
                            prompt += f"Experience from prior runs:\n{exp_txt}\n\n"
                        if few_shot_txt:
                            prompt += f"Few-shot success patterns:\n{few_shot_txt}\n\n"
                        if repo_map_txt:
                            prompt += f"Repo map (symbols):\n{repo_map_txt}\n\n"
                        if context_block:
                            prompt += f"Relevant workspace context:\n{context_block}\n\n"
                        if _looks_multifile(objective):
                            prompt += (
                                "If multiple logical units are needed, keep them in one runnable "
                                "module for sandbox, with asserts. Prefer pure functions.\n\n"
                            )
                        prompt += "Return only executable Python code, no markdown fences."
                    else:
                        result.retries += 1
                        prompt = repair_prompt(objective, generated, last_err, strategy_hint)
                        # The repair prompt is built by core/repair.py and ends
                        # with its output instruction, so the retry arm's blocks
                        # go in front of it — otherwise the re-drawn arm would
                        # once again differ only by one sentence.
                        preamble = ""
                        if repo_map_txt:
                            preamble += f"Repo map (symbols):\n{repo_map_txt}\n\n"
                        if context_block:
                            preamble += f"Relevant workspace context:\n{context_block}\n\n"
                        prompt = preamble + prompt
                        if force_burst:
                            prompt = (
                                "[Elevated model / burst retry]\n"
                                + prompt
                                + "\nInclude asserts that prove correctness.\n"
                            )

                    code_req = Envelope(
                        task_id=task_id,
                        target_gem="rose-quartz",
                        payload=RoseQuartzRequest(
                            messages=[ChatMessage(role="user", content=prompt)],
                            prefer_local=prefer_local and not force_burst,
                        ),
                    )
                    code_res = self.registry.execute(code_req)
                finally:
                    if force_burst:
                        if prev_force is None:
                            os.environ.pop("ETHER_FORCE_BURST", None)
                        else:
                            os.environ["ETHER_FORCE_BURST"] = prev_force

                self.orchestrator.process_response(code_req, code_res)
                if code_res.error or not isinstance(code_res.payload, RoseQuartzResponse):
                    return self._fail(
                        result,
                        "code",
                        code_res.error.message if code_res.error else "code failed",
                        t2,
                        attempts,
                    )
                model_used = getattr(code_res.payload, "model_used", "") or ""
                # force_burst above already flags a burst we asked for; this
                # catches the router's own fallback to burst after a local
                # failure. Matched exactly against the configured burst model —
                # substring matching on "llama" flagged every local run.
                if _is_burst_model(model_used):
                    result.used_burst = True

                generated = self._strip(code_res.payload.content)
                if len(generated) > MAX_CODE_CHARS:
                    return self._fail(
                        result,
                        "code",
                        f"Generated code exceeds {MAX_CODE_CHARS} chars",
                        t2,
                        attempts,
                    )
                result.generated_code = generated
                result.stages.append(
                    StageResult(
                        stage="code" if attempt == 1 else "code_retry",
                        success=True,
                        detail=f"{len(generated)} chars strategy={strategy} model={model_used or 'local'} burst={result.used_burst}",
                        duration_ms=(time.perf_counter() - t2) * 1000,
                    )
                )

                t3 = time.perf_counter()
                write_progress(tid, objective, "sandbox")
                sand_req = Envelope(
                    task_id=task_id,
                    target_gem="clear-quartz",
                    # The objective is what lets test_synth derive a genuinely
                    # falsifiable assertion (`name(args) == value`). It was
                    # hardcoded empty inside the sandbox, so that branch could
                    # never fire and every synthesized assert was a tautology.
                    payload=ClearQuartzRequest(code=generated, objective=objective),
                    timeout_seconds=timeout,
                )
                sand_res = self.registry.execute(sand_req)
                self.orchestrator.process_response(sand_req, sand_res)
                if sand_res.error or not isinstance(sand_res.payload, ClearQuartzResponse):
                    return self._fail(
                        result,
                        "sandbox",
                        sand_res.error.message if sand_res.error else "sandbox failed",
                        t3,
                        attempts,
                    )
                sand_payload = sand_res.payload
                result.sandbox = sand_payload
                scores = compute_scores(sand_payload)
                result.confidence = scores["confidence"]
                result.execution_score = scores["execution_score"]
                result.verification_score = scores["verification_score"]
                ok = sand_payload.exit_code == 0
                if attempt == 1 and ok:
                    result.first_compile_ok = True
                result.stages.append(
                    StageResult(
                        stage="sandbox" if attempt == 1 else "sandbox_retry",
                        success=ok,
                        detail=f"exit={sand_payload.exit_code} exec={result.execution_score} ver={result.verification_score}",
                        duration_ms=(time.perf_counter() - t3) * 1000,
                    )
                )
                if ok:
                    break
                last_err = (sand_payload.stderr or sand_payload.stdout or "non-zero exit")[:1500]
                fail_kind = classify_stderr(last_err).get("kind", "runtime")

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
            write_progress(tid, objective, "audit")
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
                crit_res = self.registry.execute(crit_req)
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
            self._credit_attempts(attempts, result)

            success = exit_code == 0
            record_outcome(success, error=None if success else (last_err or result.error))

            try:
                experience_record(
                    objective=objective,
                    code=generated or "",
                    success=success,
                    confidence=result.confidence,
                    strategy=strategy,
                    stderr=last_err if not success else "",
                    fail_kind=fail_kind if not success else "",
                    task_id=tid,
                    verification_score=result.verification_score,
                    total_tests=total_tests,
                    holdout_ok=result.holdout_ok,
                )
            except Exception:
                pass

            if not success:
                proposal = maybe_propose_fabricate()
                if proposal and not is_frozen():
                    t_fab = time.perf_counter()
                    fab_req = Envelope(
                        task_id=task_id,
                        target_gem="grandidierite",
                        payload=GrandidieriteRequest(tool_request=proposal),
                    )
                    fab_res = self.registry.execute(fab_req)
                    result.stages.append(
                        StageResult(
                            stage="auto_fabricate",
                            success=not bool(fab_res.error),
                            detail=proposal.get("name", ""),
                            duration_ms=(time.perf_counter() - t_fab) * 1000,
                        )
                    )
                elif proposal and is_frozen():
                    result.stages.append(
                        StageResult(
                            stage="auto_fabricate",
                            success=False,
                            detail="blocked_by_bench_guardian",
                        )
                    )

            if success and generated and tool_assist:
                try:
                    from gems.grandidierite.registry import run_tool

                    run_tool(
                        "save_success_pattern",
                        {
                            "objective": objective,
                            "code": generated,
                            "confidence": result.confidence,
                            "tags": [strategy],
                        },
                    )
                    cit = index_pass_pattern(
                        objective=objective,
                        code=generated,
                        confidence=result.confidence,
                        strategy=strategy,
                    )
                    # success must be DERIVED, not asserted. This was hardcoded
                    # True while the real citrine error was demoted to a
                    # substring of the detail line — which is how a memory
                    # layer that had never once stored a pattern kept
                    # reporting a green stage.
                    cit_ok = bool(cit.get("ok"))
                    detail = f"success_pattern citrine={cit_ok}"
                    if not cit_ok and cit.get("error"):
                        detail += f" error={str(cit['error'])[:200]}"
                    result.stages.append(
                        StageResult(stage="memory_save", success=cit_ok, detail=detail)
                    )
                except Exception as e:
                    # A bare `pass` here removed the row entirely, so a crash
                    # in this block looked identical to the stage never running.
                    result.stages.append(
                        StageResult(
                            stage="memory_save",
                            success=False,
                            detail=f"memory_save failed: {str(e)[:200]}",
                        )
                    )

            # Status is DERIVED from the sandbox, not asserted. This was an
            # unconditional "complete", so a run whose generated code never once
            # executed successfully still reported complete — and cli/main.py
            # (`Exit(0 if result.status == "complete" else 1)`) therefore exited
            # 0 on a total failure, while dashboard/collector.py counted it in
            # `runs_complete` and pinned pipeline_success_rate at 1.0.
            # "error" (not a third value) is deliberate: it is the vocabulary
            # _fail() and orchestrator.Status already use, so the existing
            # complete/error buckets stay exhaustive.
            if result.sandbox is not None and result.sandbox.exit_code == 0:
                result.status = "complete"
            else:
                result.status = "error"
                if not result.error:
                    detail = (last_err or "").strip()
                    result.error = f"sandbox exit {exit_code}" + (
                        f": {detail[:500]}" if detail else ""
                    )
            result.finished_at = datetime.now(timezone.utc).isoformat()
            clear_progress()
            self._persist(result)
            self._log(result)
            return result
        except Exception as e:
            return self._fail(result, "exception", str(e), run_started, attempts)

    # -- retrieval blocks ---------------------------------------------------

    def _fetch_repo_map(self, result: PipelineResult) -> str:
        t = time.perf_counter()
        text = ""
        detail = ""
        try:
            from gems.grandidierite.registry import run_tool

            rm = run_tool("repo_map", {"max_files": 40})
            if rm.get("ok"):
                files = (rm.get("files") or [])[:15]
                lines = [f["path"] + ": " + ", ".join(f.get("symbols") or []) for f in files]
                text = "\n".join(lines)[:2500]
            else:
                detail = str(rm.get("error") or "repo_map unavailable")[:120]
        except Exception as e:
            detail = str(e)[:120]
        result.stages.append(
            StageResult(
                stage="repo_map",
                success=bool(text),
                detail=detail or f"{len(text)} chars",
                duration_ms=(time.perf_counter() - t) * 1000,
            )
        )
        return text

    def _fetch_context(self, result: PipelineResult, objective: str) -> str:
        if not context_enabled():
            return ""
        t = time.perf_counter()
        try:
            block = gather_workspace_context(Path.cwd(), query=objective)
            result.stages.append(
                StageResult(
                    stage="context",
                    success=True,
                    detail=f"{len(block)} chars",
                    duration_ms=(time.perf_counter() - t) * 1000,
                )
            )
            return block
        except Exception as e:
            result.stages.append(
                StageResult(
                    stage="context",
                    success=False,
                    detail=str(e)[:120],
                    duration_ms=(time.perf_counter() - t) * 1000,
                )
            )
            return ""

    # -- bandit credit ------------------------------------------------------

    def _credit_attempts(self, attempts: List[_Attempt], result: PipelineResult) -> None:
        """One bandit update per attempt, each in its own context.

        The run reward goes to the arm that produced the code that was graded.
        Earlier attempts exist only because they failed, so they are credited
        with a failed-attempt reward in the context *they* were drawn from —
        which is what stops a successful repair from being booked against the
        arm that broke the code, and vice versa.
        """
        if not learning_enabled():
            return
        pending = [a for a in attempts if not a.credited]
        if not pending:
            return
        interim = compute_reward(
            exit_code=1,
            confidence=0.0,
            audit_approved=False,
            retries=0,
            plan_ok=result.plan_ok,
        )
        for idx, rec in enumerate(pending):
            is_final = idx == len(pending) - 1
            rec.credited = True
            self._policy_update(
                rec,
                result.reward if is_final else interim,
                result,
                attempt=idx + 1,
                final=is_final,
            )

    def _policy_update(
        self,
        rec: _Attempt,
        reward: float,
        result: PipelineResult,
        attempt: int,
        final: bool,
    ) -> None:
        exit_code = (result.sandbox.exit_code if result.sandbox else None) if final else 1
        extra = {
            "task_id": str(result.task_id),
            "objective": result.objective[:300],
            "attempt": attempt,
            "final": final,
            # Derived, because result.status is only assigned further down the
            # run; reading it here would log "complete" for a failed run.
            "status": "complete" if exit_code == 0 else "error",
            "confidence": result.confidence if final else 0.0,
            "exit_code": exit_code,
            "audit_approved": bool(result.audit and result.audit.approved) if final else None,
        }
        try:
            # Fake policies in tests define update(self, strategy, reward); only
            # pass the contextual arguments to a policy that accepts them.
            params = inspect.signature(self.policy.update).parameters
            contextual = "context" in params or any(
                p.kind == p.VAR_KEYWORD for p in params.values()
            )
        except (TypeError, ValueError):
            contextual = False
        try:
            if contextual:
                self.policy.update(
                    rec.strategy, reward, context=rec.context or None, extra=extra
                )
            else:
                self.policy.update(rec.strategy, reward)
        except Exception:
            pass

    def _fail(
        self,
        result: PipelineResult,
        stage: str,
        msg: str,
        t0: float,
        attempts: Optional[List[_Attempt]] = None,
    ) -> PipelineResult:
        result.status = "error"
        result.error = msg
        result.stages.append(
            StageResult(
                stage=stage,
                success=False,
                detail=msg,
                duration_ms=max(0.0, (time.perf_counter() - t0) * 1000),
            )
        )
        result.reward = compute_reward(
            exit_code=1,
            confidence=0.0,
            audit_approved=False,
            retries=result.retries,
            plan_ok=result.plan_ok,
            first_compile_ok=False,
            used_burst=result.used_burst,
        )
        if attempts is None and result.strategy:
            attempts = [_Attempt(strategy=result.strategy)]
        self._credit_attempts(attempts or [], result)
        try:
            experience_record(
                objective=result.objective,
                code=result.generated_code or "",
                success=False,
                confidence=0.0,
                strategy=result.strategy,
                stderr=msg,
                fail_kind=stage,
                task_id=str(result.task_id),
                verification_score=result.verification_score,
                total_tests=int(result.sandbox.total_tests) if result.sandbox else 0,
            )
        except Exception:
            pass
        try:
            record_outcome(False, error=msg)
            proposal = maybe_propose_fabricate()
            if proposal and not is_frozen():
                # The response envelope used to be discarded and success
                # hardcoded True, so a fabrication that errored out logged a
                # green auto_fabricate row. Mirrors the success path above.
                fab_res = self.registry.execute(
                    Envelope(
                        task_id=result.task_id,
                        target_gem="grandidierite",
                        payload=GrandidieriteRequest(tool_request=proposal),
                    )
                )
                fab_ok = not bool(fab_res.error)
                detail = proposal.get("name", "")
                if not fab_ok and fab_res.error:
                    detail += f" — {str(fab_res.error.message)[:160]}"
                result.stages.append(
                    StageResult(stage="auto_fabricate", success=fab_ok, detail=detail)
                )
        except Exception:
            pass
        result.finished_at = datetime.now(timezone.utc).isoformat()
        clear_progress()
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
            (self.runs_dir / f"{result.task_id}.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _log(self, result: PipelineResult, learn: bool = False) -> None:
        """Log the run to amethyst. `learn` stays False on the pipeline path.

        Passing learn=True made gems/amethyst/evolution.py update *its own*
        BanditPolicy instance after this pipeline had already updated
        `self.policy`. Both wrote the whole bandit file from a stale in-memory
        copy, so the second write silently discarded the first, and
        memory/learning/experience.jsonl collected three rows per run (two arm
        rows plus amethyst's). The arm table has exactly one owner: whoever
        made the decision. That is this pipeline.
        """
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
                            "execution_score": result.execution_score,
                            "verification_score": result.verification_score,
                            "retries": result.retries,
                            "strategy": result.strategy,
                            "strategies": list(result.strategies),
                            "reward": result.reward,
                            "used_burst": result.used_burst,
                            "first_compile_ok": result.first_compile_ok,
                            "plan_ok": result.plan_ok,
                            "experience_chars": result.experience_chars,
                            "exit_code": result.sandbox.exit_code if result.sandbox else None,
                            "audit_approved": bool(result.audit and result.audit.approved),
                            "error": result.error,
                            "learn": learn,
                        },
                    ),
                )
            )
        except Exception:
            pass
