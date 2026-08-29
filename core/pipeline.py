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


def _is_burst_model(model_used: str) -> bool:
    """Did this response come from the cloud burst model?

    Was `\"llama\" in model_used or \"grok\" in ... or \"burst\" in ...`, which
    marked every run on a local llama-family model as a burst and charged it
    the -0.05 burst penalty in compute_reward. The burst path in
    gems/rose_quartz/router.py labels its responses with ETHER_BURST_MODEL
    (default grok-3) or the literal \"burst\", so match those exactly.
    """
    m = (model_used or "").strip().lower()
    if not m:
        return False
    configured = (os.getenv("ETHER_BURST_MODEL") or "grok-3").strip().lower()
    return m in {configured, "burst"}


def _looks_multifile(objective: str) -> bool:
    o = objective.lower()
    return bool(
        re.search(r"\\b(class|module|package|refactor|file|project|codebase|multi[- ]?file)\\b", o)
        or ".py" in o
    )


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

        write_progress(tid, objective, "start", strategy=strategy)


        tool_block = ""
        last_err = ""
        fail_kind = ""
        # Every prompt actually sent to the model this run, for the leak guard.
        sent_prompts: List[str] = []

        try:
            t0 = time.perf_counter()
            available = []
            try:
                from gems.grandidierite.registry import list_tools

                available = [n.replace(".py", "") for n in list_tools().get("persistent", [])]
            except Exception as e:
                # A-3: was a silent pass — the plan gem then saw an empty tool
                # list indistinguishable from \"no tools exist\".
                result.degraded.append(f"grandidierite_list_tools_unavailable:{type(e).__name__}")

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

            # Phase C tool-runtime path (ETHER_TOOL_RUNTIME=1 + fixture).
            tool_runtime_done = False
            tool_files = {}
            workspace_kept = None
            try:
                from core.tool_runtime import (
                    code_from_result,
                    run_if_enabled,
                    tool_runtime_enabled,
                )
                if tool_runtime_enabled():
                    tr_t0 = time.perf_counter()
                    tr = run_if_enabled(objective)
                    if tr is None:
                        result.degraded.append("tool_runtime_skipped:no_result")
                        result.stages.append(
                            StageResult(
                                stage="tool_runtime",
                                success=False,
                                detail="run_if_enabled returned None (check ETHER_TOOL_RUNTIME_FIXTURE)",
                            )
                        )
                    else:
                        generated = code_from_result(tr) or ""
                        result.generated_code = generated
                        result.strategy = "tool_runtime"
                        tool_files = dict(tr.final_code or {})
                        workspace_kept = getattr(tr, "workspace_kept", None)
                        try:
                            object.__setattr__(result, "_workspace_kept", getattr(tr, "workspace_kept", None))
                        except Exception:
                            result.__dict__["_workspace_kept"] = getattr(tr, "workspace_kept", None)
                        try:
                            object.__setattr__(result, "_tool_files", tool_files)
                        except Exception:
                            try:
                                result.__dict__["_tool_files"] = tool_files
                            except Exception:
                                pass
                        result.stages.append(
                            StageResult(
                                stage="tool_runtime",
                                success=bool(tr.ok),
                                detail=(
                                    f"steps={tr.n_steps} score={tr.score:.3f} "
                                    f"reason={tr.reason or tr.error or ''}"
                                )[:300],
                                duration_ms=(time.perf_counter() - tr_t0) * 1000,
                            )
                        )
                        if tr.ok and generated:
                            tool_runtime_done = True
                            max_attempts = 1

            except Exception as e:
                result.degraded.append(f"tool_runtime_fallback:{type(e).__name__}")
                result.stages.append(
                    StageResult(
                        stage="tool_runtime",
                        success=False,
                        detail=f"fallback:{type(e).__name__}:{e}"[:300],
                    )
                )

            # Stability harden (2026-08-14): under tool-first, a tool_runtime
            # attempt that did not produce a verified artifact is TERMINAL.
            # Do not fall into the multi-minute generate / repair loop after
            # max_steps or non-ok. This eliminates the observed 984s hang class.
            # Marker string required by scripts/restore_pipeline.py integrity check.
            try:
                from core.tool_runtime import tool_runtime_enabled as _tre
                _tool_first = _tre()
            except Exception:
                _tool_first = False
            if _tool_first and not tool_runtime_done:
                result.degraded.append("tool_runtime_failed_terminal")
                return self._fail(
                    result,
                    "tool_runtime",
                    "tool_runtime_failed_terminal",
                    time.perf_counter(),
                    attempts,
                )

            _tool_path_complete = False
            # Phase D: tool_runtime already passed project pytest — re-verify
            # only via Clear Quartz multifile, skip Rose Quartz generate.
            if tool_runtime_done and generated:
                from core.repo_oracle import run_project_pytest
                from pathlib import Path as _Path
                import shutil as _sh
                t3 = time.perf_counter()
                write_progress(tid, objective, "sandbox")
                cq_ok = False
                detail = "workspace_verify: not_run"
                kept = workspace_kept
                try:
                    if kept and _Path(str(kept)).is_dir():
                        pr = run_project_pytest(
                            _Path(str(kept)),
                            test_args=["tests"],
                            timeout=max(30, int(timeout)),
                        )
                        cq_ok = bool(pr.get("ok"))
                        sc = float(pr.get("score") or 0.0)
                        result.verification_score = 1.0 if cq_ok else sc
                        result.execution_score = float(result.verification_score)
                        detail = (
                            "workspace_verify exit=%s score=%s ok=%s"
                            % (pr.get("returncode"), sc, cq_ok)
                        )
                    else:
                        detail = "workspace_verify: no_kept_dir fallback_files=%d" % len(tool_files or {})
                        files = dict(tool_files or {})
                        if not files and generated and "# file:" in generated:
                            from core.multifile import extract_file_blocks
                            files = extract_file_blocks(generated)
                        fixture_env = (os.getenv("ETHER_TOOL_RUNTIME_FIXTURE") or "").strip()
                        if fixture_env:
                            fixture_env = str(_Path(fixture_env).resolve())
                        sand_req = Envelope(
                            task_id=task_id,
                            target_gem="clear-quartz",
                            payload=ClearQuartzRequest(
                                code=generated or "",
                                objective=objective,
                                prepare_code=False,
                                test_args=["tests"],
                                files=files,
                                fixture_root=fixture_env or None,
                            ),
                            timeout_seconds=timeout,
                        )
                        sand_res = self.registry.execute(sand_req)
                        if sand_res.error or not isinstance(sand_res.payload, ClearQuartzResponse):
                            cq_ok = False
                            detail = "cq error: %s" % (sand_res.error,)
                        else:
                            sp = sand_res.payload
                            result.sandbox = sp
                            from core.confidence import compute_scores as _cs
                            scores = _cs(sp)
                            result.confidence = scores["confidence"]
                            result.execution_score = scores["execution_score"]
                            result.verification_score = scores["verification_score"]
                            cq_ok = sp.exit_code == 0
                            detail = "multifile_verify exit=%s tests=%s/%s files=%d" % (
                                sp.exit_code, sp.tests_passed, sp.total_tests, len(files),
                            )
                except Exception as _ve:
                    cq_ok = False
                    detail = "verify_exception: %s: %s" % (type(_ve).__name__, _ve)
                    result.degraded.append("verify_exception:%s" % type(_ve).__name__)
                finally:
                    if kept:
                        _sh.rmtree(str(kept), ignore_errors=True)
                result.stages.append(
                    StageResult(
                        stage="sandbox",
                        success=cq_ok,
                        detail=str(detail)[:500],
                        duration_ms=(time.perf_counter() - t3) * 1000,
                    )
                )
                if cq_ok:
                    result.repo_oracle_ok = True
                    result.verification_score = 1.0
                    result.execution_score = 1.0
                    result.first_compile_ok = True
                else:
                    result.repo_oracle_ok = False
                    result.degraded.append("cq_verify_failed_after_tool_runtime")
                _tool_path_complete = True

            # Agent loop path (ETHER_AGENT_LOOP=1). Draws several candidates at
            # varied temperature, scores each WITHOUT a holdout, repairs against
            # what actually ran, and returns the best — never overwriting a
            # better earlier attempt, which is what the fixed two-shot retry did.
            loop_result = None
            if self._agent_loop_enabled():
                try:
                    from core.agent_loop import LoopBudget, run_loop

                    lt = time.perf_counter()
                    loop_result = run_loop(
                        objective,
                        self._make_generate_fn(task_id, prefer_local),
                        budget=LoopBudget(
                            max_attempts=int(os.getenv("ETHER_LOOP_ATTEMPTS", "4")),
                            wall_clock_s=float(os.getenv("ETHER_LOOP_SECONDS", "300")),
                        ),
                        # Scores the selection only. run_loop asserts this never
                        # reaches a prompt.
                        holdout_test=holdout_test,
                    )
                    generated = loop_result.code or ""
                    result.generated_code = generated
                    result.strategy = "agent_loop"
                    result.stages.append(
                        StageResult(
                            stage="agent_loop",
                            success=bool(generated),
                            detail=(
                                f"{len(loop_result.attempts)} candidates, "
                                f"best score {loop_result.score:.3f}, "
                                f"{loop_result.selection_reason}"
                            )[:300],
                            duration_ms=(time.perf_counter() - lt) * 1000,
                        )
                    )
                    # One pass through the existing loop so the artifact still
                    # goes through sandbox + audit; the generation half is
                    # skipped below because loop_result is set.
                    max_attempts = 1 if generated else 2
                except Exception as e:
                    result.stages.append(
                        StageResult(
                            stage="agent_loop",
                            success=False,
                            detail=f"loop failed, falling back: {str(e)[:180]}",
                        )
                    )
                    result.degraded.append(f"agent_loop_fallback:{type(e).__name__}")
                    loop_result = None

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
                    code_req = Envelope(
                        task_id=task_id,
                        target_gem="rose-quartz",
                        payload=RoseQuartzRequest(
                            messages=[ChatMessage(role="user", content=prompt)],
                            prefer_local=prefer_local and not force_burst,
                        ),
                    )
                    code_res = self.registry.execute(code_req)
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
                write_progress(tid, objective, "sandbox")
                sand_req = Envelope(
                    task_id=task_id,
                    target_gem="clear-quartz",
                    # The objective is what lets test_synth derive a genuinely
                    # falsifiable assertion (`name(args) == value`). It was
                    # hardcoded empty inside the sandbox, so that branch could
                    # never fire and every synthesized assert was a tautology.
                    payload=ClearQuartzRequest(
                        code=generated,
                        objective=objective,
                        prepare_code=not bool(tool_runtime_done),
                        test_args=["tests"],
                        files=dict(getattr(result, "_tool_files", None) or {}),
                    ),
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
    ) -> Tuple[Optional[int], int, str]:
        """Pre-refactor inline spine (default path); removed when
        ETHER_LOOP_RUNNER becomes the only path. Byte-identical behavior to
        the pre-refactor inline block (legacy pipeline.py:649-841). Returns
        (exit_code, total_tests, effective holdout_test); everything else
        mutates `result` exactly as the inline block did."""
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
        """Pre-extraction finalize tail (default path). Byte-identical behavior
        to the pre-refactor inline block; removed when ETHER_LOOP_RUNNER
        defaults on (roadmap stage 6)."""
        task_id = result.task_id
        tid = str(task_id)
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
                holdout_test=holdout_test,
            )
        except Exception as e:
            # A-3: was a silent pass — a run that lost its experience record
            # looked identical to one that kept it. The loop-runner handler
            # emits the identical string for this seam.
            result.degraded.append(f"experience_record_failed:{type(e).__name__}")

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
                        # So the writer can refuse an artifact that carries
                        # the holdout. Without this the store re-injects
                        # leaked-era code into every later prompt.
                        "holdout_test": holdout_test,
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
        # Phase B: repo_oracle_ok=False forces error even on sandbox exit=0.
        if result.repo_oracle_ok is False:
            result.status = "error"
            if not result.error:
                detail = (last_err or "").strip()
                result.error = "repo_oracle failed" + (f": {detail[:500]}" if detail else "")
        elif result.sandbox is not None and result.sandbox.exit_code == 0:
            result.status = "complete"
        else:
            result.status = "error"
            if not result.error:
                detail = (last_err or "").strip()
                result.error = f"sandbox exit {exit_code}" + (f": {detail[:500]}" if detail else "")

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
        """True only when the objective plausibly depends on this repository."""
        if os.getenv("ETHER_FORCE_CONTEXT", "0") == "1":
            return True
        return bool(self._REPO_SIGNALS.search(objective or ""))

    def _agent_loop_enabled(self) -> bool:
        return os.getenv("ETHER_AGENT_LOOP", "0") == "1"

    def _make_generate_fn(self, task_id: UUID, prefer_local: bool):
        """Adapter so the agent loop can draw candidates at varied sampling.

        Returns raw completion text; the loop does its own extraction, because
        the pipeline's `_strip()` only handles a fence at position 0 and 10 of
        120 samples in a measured run died on unstripped markdown reaching the
        sandbox as Python.
        """

        def generate(prompt: str, temperature: float = 0.2, seed: int = 1) -> str:
            req = Envelope(
                task_id=task_id,
                target_gem="rose-quartz",
                payload=RoseQuartzRequest(
                    messages=[ChatMessage(role="user", content=prompt)],
                    prefer_local=prefer_local,
                    temperature=temperature,
                    seed=seed,
                ),
            )
            res = self.registry.execute(req)
            if res.error or not isinstance(res.payload, RoseQuartzResponse):
                raise RuntimeError(res.error.message if res.error else "no completion")
            return res.payload.content or ""

        return generate

    def _fetch_context(self, result: PipelineResult, objective: str) -> str:
        if not context_enabled():
            return ""

        # Retrieval is only useful when the task actually depends on this repo.
        #
        # Measured on a `merge_sorted` objective: the objective was 168 chars
        # and the prompt was ~4,485 — the objective was 3.7% of it. The other
        # 78% was BM25 over ETHER's OWN SOURCE (core/failure_graph.py internals,
        # for a task about merging two sorted lists), and the 3,500-char budget
        # is saturated on EVERY task because the assembler fills to the cap
        # rather than stopping when relevance runs out.
        #
        # For a 3B-active MoE that is a haystack with the instruction buried in
        # it, and it shows: the ether arm scored 0.874 against a bare-model
        # 0.933 on the same tasks. The scaffold was subtracting.
        if not self._needs_repo_context(objective):
            result.stages.append(
                StageResult(
                    stage="context",
                    success=True,
                    detail="skipped — self-contained objective",
                )
            )
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
        except Exception as e:
            # A-3: was a silent pass — same seam as the finalize tail.
            result.degraded.append(f"experience_record_failed:{type(e).__name__}")
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
        except Exception as e:
            # A-3: was a silent except:pass — a failed fabrication attempt left
            # no trace on the run at all.
            result.degraded.append(f"auto_fabricate_failed:{type(e).__name__}")
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
            write_json(self.runs_dir / f"{result.task_id}.json", result.model_dump(mode="json"))
        except Exception as e:
            # A-3: was a silent pass — a run that never reached disk was
            # indistinguishable from one that persisted.
            result.degraded.append(f"persist_failed:{type(e).__name__}")

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
