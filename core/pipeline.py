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

            from core.loop.execute_plan import execute_selenite_plan

            _pl = execute_selenite_plan(
                self,
                result,
                skip=skip,
                objective=objective,
                tid=tid,
                task_id=task_id,
                available=available,
                write_progress=write_progress,
                attempts=attempts,
                t0=t0,
            )
            if _pl.get("fail") is not None:
                return _pl["fail"]
            plan_res = _pl.get("plan_res")
            needs_tool = bool(_pl.get("needs_tool"))

            from core.loop.extend_stage import run_extend_if_needed
            from core.loop.retrieval import load_retrieval, make_lazy_blocks

            tool_block = run_extend_if_needed(
                self,
                result,
                plan_res=plan_res,
                needs_tool=needs_tool,
                task_id=task_id,
                tid=tid,
                write_progress=write_progress,
            )
            few_shot, exp_block = load_retrieval(
                result,
                objective=objective,
                tool_assist=tool_assist,
                tid=tid,
                write_progress=write_progress,
            )
            repo_map_block, workspace_block = make_lazy_blocks(
                self,
                result,
                tool_assist=tool_assist,
                tid=tid,
                objective=objective,
                write_progress=write_progress,
            )

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

            from core.loop.generate_retry_loop import run_generate_retry_loop

            st = {
                "attempt": attempt,
                "max_attempts": max_attempts,
                "_tool_path_complete": _tool_path_complete,
                "generated": generated or "",
                "tool_runtime_done": tool_runtime_done,
                "loop_result": loop_result,
                "tid": tid,
                "objective": objective,
                "strategy": strategy,
                "strategy_hint": strategy_hint,
                "fail_kind": fail_kind,
                "last_err": last_err,
                "skip": skip,
                "timeout": timeout,
                "prefer_local": prefer_local,
                "task_id": task_id,
                "sent_prompts": sent_prompts,
                "attempts": attempts,
                "tool_block": tool_block,
                "exp_block": exp_block,
                "few_shot": few_shot,
                "ok": False,
            }
            st = run_generate_retry_loop(
                self,
                result,
                write_progress=write_progress,
                repo_map_block=repo_map_block,
                workspace_block=workspace_block,
                st=st,
            )
            attempt = st["attempt"]
            generated = st["generated"]
            strategy = st["strategy"]
            strategy_hint = st["strategy_hint"]
            fail_kind = st["fail_kind"]
            last_err = st["last_err"]
            ok = st["ok"]
            sent_prompts = st["sent_prompts"]
            attempts = st["attempts"]

            from core.loop.close_run import close_run

            return close_run(
                self,
                result,
                tid=tid,
                objective=objective,
                generated=generated or "",
                tool_assist=tool_assist,
                critique=critique,
                holdout_test=holdout_test,
                sent_prompts=sent_prompts,
                skip=skip,
                last_err=last_err,
                fail_kind=fail_kind,
                strategy=strategy,
                attempts=attempts,
                _tool_path_complete=_tool_path_complete,
            )
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
        from core.loop.persist_run import persist_run

        persist_run(self, result)

    def _log(self, result: PipelineResult, learn: bool = False) -> None:
        from core.loop.log_run import log_run

        log_run(self, result, learn)
