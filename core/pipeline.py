"""End-to-end pipeline: experience, process rewards, burst-on-retry, multifile assist."""

from __future__ import annotations

import inspect
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
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
from core.loop import loop_runner_enabled
from core.loop.handlers.finalize import FinalizeContext
from core.loop.handlers.verify import VerificationContext
from core.loop.runner import LoopRunner
from core.loop.gems_call import audit_execute, rose_complete, sandbox_execute
from core.spine.state_io import write_json

MAX_CODE_CHARS = 50_000


class _LoopAlreadyGenerated(Exception):
    """Control flow: the agent loop produced the artifact; skip legacy generation."""


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
    # Phase B: set when ETHER_REPO_ORACLE is active; False forces repair/retry.
    repo_oracle_ok: Optional[bool] = None
    confidence: float = 0.0
    execution_score: float = 0.0
    verification_score: float = 0.0
    status: str = "complete"
    error: Optional[str] = None
    stages: List[StageResult] = Field(default_factory=list)
    # A-3: capability losses that used to vanish into except:pass. Seeded from
    # the registry (citrine) and appended at each degraded seam.
    # NOTE: Field(default=[]) not default_factory=list — the stage-1
    # acceptance probe reads model_fields["degraded"].default and requires [].
    # pydantic v2 deep-copies mutable defaults per instance, so this is safe.
    degraded: List[str] = Field(default=[])
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


from core.loop.pipeline_util import is_burst_model as _is_burst_model
from core.loop.pipeline_util import looks_multifile as _looks_multifile
from core.loop.pipeline_util import strip_fences


# Anchored on the repo root, not the CWD. `Path(\"memory/runs\")` meant that
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
        # Capabilities that failed to register (A-3); every run's degraded
        # list is seeded from this so the loss is visible on the result.
        self._registry_degraded = list(getattr(self.registry, "degraded", []))
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
        # measured the interval from \"now\" to \"now\" and always logged ~0ms.
        run_started = time.perf_counter()
        self.orchestrator.start(task_id)
        result = PipelineResult(
            task_id=task_id,
            objective=objective,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        result.degraded = list(self._registry_degraded)
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

        # Shadow write_progress for this run so every stage also lands a checkpoint.
        # I-010: Pipeline.run was the last unwired caller of checkpoint.py.
        from core.progress import write_progress as _write_progress

        def write_progress(task_id: str, objective: str, stage: str, detail: str = "", **extra: Any) -> None:
            _write_progress(task_id, objective, stage, detail, **extra)
            try:
                from core.checkpoint import checkpoint_pipeline

                payload = {"strategy": result.strategy}
                if detail:
                    payload["detail"] = str(detail)[:120]
                for key, val in extra.items():
                    payload[str(key)[:40]] = str(val)[:80]
                checkpoint_pipeline(
                    run_id=str(task_id),
                    stage=stage,
                    objective=objective,
                    n_stages=len(result.stages),
                    extra=payload,
                )
            except Exception:
                pass

        from core.loop.begin import start_resume_gems
        from core.loop.gems_call import audit_execute, rose_complete, sandbox_execute
        from core.loop.stage_mark import skip_detail

        skip = start_resume_gems(result, tid, objective, strategy, write_progress)



        tool_block = ""
        last_err = ""
        fail_kind = ""
        # Every prompt actually sent to the model this run, for the leak guard.
        sent_prompts: List[str] = []

        try:
            t0 = time.perf_counter()
            from core.loop.tools_avail import available_tools

            available = available_tools(result)

            from core.loop.plan_stage import apply_plan_skip, walk_current_plan

            plan_res = None
            if apply_plan_skip(skip, objective, result, write_progress, tid):
                pass
            else:
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
            try:
                walk_current_plan(result, tid, objective, write_progress)
            except Exception as exc:
                result.degraded.append(f"plan_walk:{type(exc).__name__}")
            needs_tool = bool(
                plan_res is not None
                and getattr(plan_res.payload, "needs_tool", False)
            )
            result.stages.append(
                StageResult(
                    stage="plan",
                    success=True,
                    detail=f"{len(result.plan.steps)} steps tool={needs_tool}",
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )
            )

            if needs_tool and plan_res is not None and plan_res.payload.tool_request:
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

            from core.loop.tool_runtime_path import run_tool_runtime_path

            _tr = run_tool_runtime_path(
                self,
                result,
                objective=objective,
                timeout=timeout,
                skip=skip,
                tid=tid,
                task_id=task_id,
                attempts=attempts,
                generated=generated or "",
                write_progress=write_progress,
            )
            generated = _tr.get("generated") or generated
            tool_runtime_done = bool(_tr.get("tool_runtime_done"))
            _tool_path_complete = bool(_tr.get("tool_path_complete"))
            if _tr.get("max_attempts") is not None:
                max_attempts = int(_tr["max_attempts"])
            if _tr.get("fail") is not None:
                return _tr["fail"]

            from core.loop.agent_loop_path import run_agent_loop_path

            _al = run_agent_loop_path(
                self,
                result,
                objective=objective,
                task_id=task_id,
                prefer_local=prefer_local,
                holdout_test=holdout_test,
                generated=generated or "",
            )
            loop_result = _al.get("loop_result")
            generated = _al.get("generated") or generated
            if _al.get("max_attempts") is not None:
                max_attempts = int(_al["max_attempts"])

            while attempt < max_attempts and not _tool_path_complete:
                attempt += 1
                t2 = time.perf_counter()
                write_progress(tid, objective, "code" if attempt == 1 else "code_retry")

                if tool_runtime_done and generated:
                    pass
                elif loop_result is not None and generated:
                    # The agent loop already generated, verified and selected.
                    # Fall through to sandbox + audit without re-drawing.
                    pass
                elif attempt > 1:
                    # Re-draw the arm now that a failure class exists. This is
                    # the whole point of the fail_kind feature: at first
                    # selection nothing has failed yet, so the repair branch of
                    # the policy could never fire.
                    strategy, strategy_ctx = select_strategy_with_context(
                        objective, self.policy, fail_kind=fail_kind
                    )
                    attempts.append(_Attempt(strategy=strategy, context=strategy_ctx))
                    if not tool_runtime_done:
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
                        from core.loop.generate_retry import first_prompt

                        prompt = first_prompt(
                            objective,
                            strategy_hint,
                            result.plan.model_dump_json(indent=2),
                            tool_block=tool_block,
                            exp_txt=exp_txt,
                            few_shot_txt=few_shot_txt,
                            repo_map_txt=repo_map_txt,
                            context_block=context_block,
                            multifile=_looks_multifile(objective),
                        )
                    else:
                        from core.loop.generate_retry import retry_prompt as build_retry

                        result.retries += 1
                        prompt = build_retry(
                            objective,
                            generated,
                            last_err,
                            strategy_hint,
                            repo_map_txt=repo_map_txt,
                            context_block=context_block,
                            burst=force_burst,
                        )

                    if tool_runtime_done and generated:
                        code_res = None
                        raise _LoopAlreadyGenerated
                    if loop_result is not None and generated:
                        # The agent loop drew, verified and selected already.
                        # Record its prompts for the leak guard and skip the
                        # legacy single-shot generation entirely.
                        for _a in loop_result.attempts:
                            _p = getattr(_a, "prompt", "")
                            if _p:
                                sent_prompts.append(_p)
                        code_res = None
                        raise _LoopAlreadyGenerated

                    # Kept so the prompt guard can inspect exactly what the
                    # model was shown, rather than trusting that every leak
                    # channel was closed at its source.
                    sent_prompts.append(prompt)
                    code_req, code_res = rose_complete(
                        self.registry,
                        task_id=task_id,
                        prompt=prompt,
                        prefer_local=prefer_local and not force_burst,
                    )
                except _LoopAlreadyGenerated:
                    # Not an error: the agent loop already produced and selected
                    # the artifact. Swallow the control-flow signal here so the
                    # run continues into sandbox + audit.
                    code_res = None
                finally:
                    if force_burst:
                        if prev_force is None:
                            os.environ.pop("ETHER_FORCE_BURST", None)
                        else:
                            os.environ["ETHER_FORCE_BURST"] = prev_force

                if code_res is None:
                    # Loop path: artifact already in `generated`; go to sandbox.
                    pass
                else:
                    self.orchestrator.process_response(code_req, code_res)
                if code_res is not None and (code_res.error or not isinstance(code_res.payload, RoseQuartzResponse)):
                    return self._fail(
                        result,
                        "code",
                        code_res.error.message if code_res.error else "code failed",
                        t2,
                        attempts,
                    )
                if code_res is None:
                    # Agent-loop path: `generated` is already the selected
                    # candidate and the loop did its own extraction, which
                    # handles fences and prose that _strip() does not.
                    model_used = os.getenv("ETHER_PRIMARY_MODEL", "") or "local"
                else:
                    model_used = getattr(code_res.payload, "model_used", "") or ""
                # force_burst above already flags a burst we asked for; this
                # catches the router's own fallback to burst after a local
                # failure. Matched exactly against the configured burst model —
                # substring matching on "llama" flagged every local run.
                if _is_burst_model(model_used):
                    result.used_burst = True

                if code_res is not None:
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
                write_progress(
                    tid,
                    objective,
                    "sandbox",
                    detail=skip_detail(skip, "sandbox"),
                )
                sand_req, sand_res = sandbox_execute(
                    self.registry,
                    task_id=task_id,
                    generated=generated,
                    objective=objective,
                    timeout=timeout,
                    files=dict(getattr(result, "_tool_files", None) or {}),
                    prepare_code=not bool(tool_runtime_done),
                    orchestrator=self.orchestrator,
                )
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
                # Phase B: project-pytest oracle — fail even when sandbox exit=0.
                if ok:
                    from core.pipeline_hooks import apply_repo_oracle_gate

                    gate = apply_repo_oracle_gate(
                        generated,
                        objective,
                        execution_score=result.execution_score,
                        verification_score=result.verification_score,
                        confidence=result.confidence,
                    )
                    if gate.get("active"):
                        result.repo_oracle_ok = gate.get("repo_oracle_ok")
                        result.verification_score = float(gate["verification_score"])
                        result.confidence = float(gate["confidence"])
                        result.stages.append(
                            StageResult(
                                stage="repo_oracle",
                                success=bool(gate.get("ok")),
                                detail=str(gate.get("detail") or "")[:240],
                            )
                        )
                        if not gate.get("ok"):
                            ok = False
                            last_err = str(gate.get("last_err") or "repo_oracle failed")[:1500]
                            fail_kind = str(gate.get("fail_kind") or "repo_oracle")
                if ok:
                    break
                if fail_kind != "repo_oracle":
                    last_err = (sand_payload.stderr or sand_payload.stdout or "non-zero exit")[:1500]
                    fail_kind = classify_stderr(last_err).get("kind", "runtime")

            if _tool_path_complete:
                exit_code = 0 if result.repo_oracle_ok else 1
                total_tests = (
                    int(getattr(result.sandbox, "total_tests", 0) or 0) if result.sandbox else 0
                )
            elif loop_runner_enabled():
                _out = LoopRunner(registry=self.registry).run_verify(
                    VerificationContext(
                        task_id=tid,
                        objective=objective,
                        generated=generated or "",
                        tool_assist=tool_assist,
                        critique=critique,
                        holdout_test=holdout_test,
                        sent_prompts=sent_prompts,
                        has_sandbox=result.sandbox is not None,
                        sandbox_exit=result.sandbox.exit_code if result.sandbox else None,
                        sandbox_total_tests=int(result.sandbox.total_tests)
                        if result.sandbox
                        else 0,
                        confidence=result.confidence,
                        verification_score=result.verification_score,
                        retries=result.retries,
                        plan_ok=result.plan_ok,
                        first_compile_ok=result.first_compile_ok,
                        used_burst=result.used_burst,
                    )
                )
                for _s in _out.stages:
                    result.stages.append(StageResult(**_s))
                result.confidence = _out.confidence
                if _out.audit is not None:
                    result.audit = BlackTourmalineResponse.model_validate(_out.audit)
                if _out.critique is not None:
                    result.critique = LabradoriteResponse.model_validate(_out.critique)
                result.holdout_ok = _out.holdout_ok
                result.reward = _out.reward
                exit_code, total_tests, holdout_test = (
                    _out.exit_code,
                    _out.total_tests,
                    _out.holdout_test,
                )
            else:
                exit_code, total_tests, holdout_test = self._verify_legacy(
                    result,
                    objective=objective,
                    generated=generated or "",
                    critique=critique,
                    holdout_test=holdout_test,
                    sent_prompts=sent_prompts,
                    tool_assist=tool_assist,
                    skip=skip,
                )
            self._credit_attempts(attempts, result)

            if loop_runner_enabled():
                outcome = LoopRunner(
                    registry=self.registry,
                ).run_finalize(
                    FinalizeContext(
                        task_id=tid,
                        objective=objective,
                        generated=generated or "",
                        success=(exit_code == 0),
                        last_err=last_err,
                        fail_kind=fail_kind,
                        strategy=strategy,
                        confidence=result.confidence,
                        verification_score=result.verification_score,
                        total_tests=total_tests,
                        holdout_ok=result.holdout_ok,
                        holdout_test=holdout_test,
                        tool_assist=tool_assist,
                        has_sandbox=result.sandbox is not None,
                        exit_code=exit_code,
                        result_error=result.error,
                    )
                )
                for _s in outcome.stages:
                    result.stages.append(StageResult(**_s))
                result.degraded.extend(outcome.degraded)
                result.status = outcome.status
                if outcome.error is not None:
                    result.error = outcome.error
            else:
                self._finalize_legacy(
                    result,
                    objective=objective,
                    generated=generated or "",
                    last_err=last_err,
                    fail_kind=fail_kind,
                    strategy=strategy,
                    total_tests=total_tests,
                    holdout_test=holdout_test,
                    tool_assist=tool_assist,
                    exit_code=exit_code,
                )
            result.finished_at = datetime.now(timezone.utc).isoformat()
            clear_progress()
            self._persist(result)
            self._log(result)
            return result
        except Exception as e:
            return self._fail(result, "exception", str(e), run_started, attempts)

    def _verify_legacy(
        self,
        result: PipelineResult,
        *,
        objective: str,
        generated: str,
        critique: bool,
        holdout_test: str,
        sent_prompts: List[str],
        tool_assist: bool,
        skip: Optional[set] = None,
    ) -> Tuple[Optional[int], int, str]:
        from core.loop.verify_legacy import verify_legacy

        return verify_legacy(
            self.registry,
            result,
            objective=objective,
            generated=generated,
            critique=critique,
            holdout_test=holdout_test,
            sent_prompts=sent_prompts,
            tool_assist=tool_assist,
            skip=skip,
        )

    def _finalize_legacy(
        self,
        result: PipelineResult,
        *,
        objective: str,
        generated: str,
        last_err: str,
        fail_kind: str,
        strategy: str,
        total_tests: int,
        holdout_test: str,
        tool_assist: bool,
        exit_code: Optional[int],
    ) -> None:
        from core.loop.finalize_legacy import finalize_legacy

        finalize_legacy(
            self.registry,
            result,
            objective=objective,
            generated=generated,
            last_err=last_err,
            fail_kind=fail_kind,
            strategy=strategy,
            total_tests=total_tests,
            holdout_test=holdout_test,
            tool_assist=tool_assist,
            exit_code=exit_code,
        )

    # -- retrieval blocks ---------------------------------------------------

    def _fetch_repo_map(self, result: PipelineResult) -> str:
        from core.loop.retrieve import fetch_repo_map

        return fetch_repo_map(result)

    # Signals that an objective refers to THIS codebase rather than asking for
    # a self-contained function. Deliberately narrow: the failure mode being
    # fixed is injecting 3,500 chars of unrelated source into every prompt, so
    # the default must be "no context" and the exception must be earned.
    _REPO_SIGNALS = re.compile(
        r"\\b(this repo|this codebase|this project|existing|refactor|the file|"
        r"our |src/|core/|gems/|scripts/|tests/|\\.py\\b|module\\b|package\\b|"
        r"import from|update the|modify the|fix the bug in)\\b",
        re.IGNORECASE,
    )

    def _needs_repo_context(self, objective: str) -> bool:
        from core.loop.retrieve import needs_repo_context

        return needs_repo_context(objective)

    def _agent_loop_enabled(self) -> bool:
        from core.loop.generate_fn import agent_loop_enabled

        return agent_loop_enabled()

    def _make_generate_fn(self, task_id: UUID, prefer_local: bool):
        from core.loop.generate_fn import make_generate_fn

        return make_generate_fn(self, task_id, prefer_local)

    def _fetch_context(self, result: PipelineResult, objective: str) -> str:
        from core.loop.retrieve import fetch_context

        return fetch_context(result, objective)

    # -- bandit credit ------------------------------------------------------

    def _credit_attempts(self, attempts: List[_Attempt], result: PipelineResult) -> None:
        from core.loop.bandit_credit import credit_attempts

        credit_attempts(self, attempts, result)

    def _policy_update(
        self,
        rec: _Attempt,
        reward: float,
        result: PipelineResult,
        attempt: int,
        final: bool,
    ) -> None:
        from core.loop.bandit_credit import policy_update

        policy_update(self, rec, reward, result, attempt, final)

    def _fail(
        self,
        result: PipelineResult,
        stage: str,
        msg: str,
        t0: float,
        attempts: Optional[List[_Attempt]] = None,
    ) -> PipelineResult:
        from core.loop.fail_run import fail_run

        return fail_run(self, result, stage, msg, t0, attempts)

    def _strip(self, text: str) -> str:
        return strip_fences(text)

    def _persist(self, result: PipelineResult) -> None:
        try:
            write_json(self.runs_dir / f"{result.task_id}.json", result.model_dump(mode="json"))
        except Exception as e:
            # A-3: was a silent pass — a run that never reached disk was
            # indistinguishable from one that persisted.
            result.degraded.append(f"persist_failed:{type(e).__name__}")

    def _log(self, result: PipelineResult, learn: bool = False) -> None:
        from core.loop.log_run import log_run

        log_run(self, result, learn)
