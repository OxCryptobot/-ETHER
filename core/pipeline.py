"""End-to-end pipeline: experience, process rewards, burst-on-retry, multifile assist."""

from __future__ import annotations

import os
import re
import time
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
    GrandidieriteRequest,
    ChatMessage,
    ExecutionPlan,
)
from core.registry import GemRegistry, build_default_registry
from core.orchestrator import Orchestrator
from core.confidence import compute_scores
from core.context import gather_workspace_context, context_enabled
from core.learning import BanditPolicy, compute_reward, learning_enabled, strategy_prompt_addon
from core.fail_streak import record_outcome, maybe_propose_fabricate
from core.progress import write_progress, clear_progress
from core.repair import repair_prompt, classify_stderr
from core.patterns import index_pass_pattern
from core.experience import retrieve as experience_retrieve, record as experience_record
from core.bench_guardian import is_frozen
from core.pipeline_burst import decide_burst

MAX_CODE_CHARS = 50_000


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
    strategy: str = "default"
    reward: float = 0.0
    few_shot_chars: int = 0
    tool_output_chars: int = 0
    experience_chars: int = 0
    used_burst: bool = False
    first_compile_ok: bool = False
    plan_ok: bool = False
    started_at: str = ""
    finished_at: str = ""


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
        self.orchestrator.start(task_id)
        result = PipelineResult(
            task_id=task_id,
            objective=objective,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        timeout = int(os.getenv("ETHER_SANDBOX_TIMEOUT", "120"))
        allow_retry = os.getenv("ETHER_SANDBOX_RETRY", "1") == "1"
        tool_assist = os.getenv("ETHER_TOOL_ASSIST", "1") == "1"

        strategy = self.policy.select() if learning_enabled() else "default"
        result.strategy = strategy
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
                    result, "plan", plan_res.error.message if plan_res.error else "plan failed", t0
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

            few_shot = ""
            repo_map_txt = ""
            exp_block = ""
            if tool_assist:
                t_ta = time.perf_counter()
                write_progress(tid, objective, "tool_assist")
                try:
                    from gems.grandidierite.registry import run_tool

                    fs = run_tool("few_shot_pack", {"query": objective, "top_k": 2})
                    if fs.get("ok") and isinstance(fs.get("result"), dict):
                        few_shot = fs["result"].get("block") or ""
                        result.few_shot_chars = len(few_shot)
                    if _looks_multifile(objective) or strategy == "repo_map_on":
                        rm = run_tool("repo_map", {"max_files": 40})
                        if rm.get("ok"):
                            files = (rm.get("files") or [])[:15]
                            lines = [
                                f["path"] + ": " + ", ".join(f.get("symbols") or []) for f in files
                            ]
                            repo_map_txt = "\n".join(lines)[:2500]
                    exp = experience_retrieve(objective, k=3)
                    exp_block = exp.get("block") or ""
                    result.experience_chars = len(exp_block)
                    result.stages.append(
                        StageResult(
                            stage="tool_assist",
                            success=True,
                            detail=(
                                f"few_shot={result.few_shot_chars}c map={len(repo_map_txt)}c "
                                f"exp={result.experience_chars}c"
                            ),
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

            context_block = ""
            use_ctx = context_enabled() and strategy != "no_context"
            if use_ctx:
                tctx = time.perf_counter()
                write_progress(tid, objective, "context")
                try:
                    context_block = gather_workspace_context(Path.cwd(), query=objective)
                    result.context_chars = len(context_block)
                    result.stages.append(
                        StageResult(
                            stage="context",
                            success=True,
                            detail=f"{result.context_chars} chars",
                            duration_ms=(time.perf_counter() - tctx) * 1000,
                        )
                    )
                except Exception as e:
                    result.stages.append(
                        StageResult(
                            stage="context",
                            success=False,
                            detail=str(e)[:120],
                            duration_ms=(time.perf_counter() - tctx) * 1000,
                        )
                    )

            generated = ""
            attempt = 0
            max_attempts = 2 if allow_retry else 1
            strategy_hint = strategy_prompt_addon(strategy)

            while attempt < max_attempts:
                attempt += 1
                t2 = time.perf_counter()
                write_progress(tid, objective, "code" if attempt == 1 else "code_retry")

                # Single policy entry point — no duplicated inline rules
                force_burst = decide_burst(
                    attempt=attempt,
                    strategy=strategy,
                    objective=objective,
                    tier=0,
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
                        if exp_block:
                            prompt += f"Experience from prior runs:\n{exp_block}\n\n"
                        if few_shot:
                            prompt += f"Few-shot success patterns:\n{few_shot}\n\n"
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
                        result, "code", code_res.error.message if code_res.error else "code failed", t2
                    )
                model_used = getattr(code_res.payload, "model_used", "") or ""
                if model_used and model_used != os.getenv("ETHER_PRIMARY_MODEL", ""):
                    if "llama" in model_used.lower() or "grok" in model_used.lower() or "burst" in model_used.lower():
                        result.used_burst = True

                generated = self._strip(code_res.payload.content)
                if len(generated) > MAX_CODE_CHARS:
                    return self._fail(result, "code", f"Generated code exceeds {MAX_CODE_CHARS} chars", t2)
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
                    payload=ClearQuartzRequest(code=generated),
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

            exit_code = result.sandbox.exit_code if result.sandbox else None
            audit_ok = bool(result.audit and result.audit.approved)
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
            if learning_enabled():
                self.policy.update(strategy, result.reward)

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

            result.status = "complete"
            result.finished_at = datetime.now(timezone.utc).isoformat()
            clear_progress()
            self._persist(result)
            self._log(result, learn=True)
            return result
        except Exception as e:
            return self._fail(result, "exception", str(e), time.perf_counter())

    def _fail(self, result: PipelineResult, stage: str, msg: str, t0: float) -> PipelineResult:
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
        if learning_enabled() and result.strategy:
            try:
                self.policy.update(result.strategy, result.reward)
            except Exception:
                pass
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
                self.registry.execute(
                    Envelope(
                        task_id=result.task_id,
                        target_gem="grandidierite",
                        payload=GrandidieriteRequest(tool_request=proposal),
                    )
                )
                result.stages.append(
                    StageResult(stage="auto_fabricate", success=True, detail=proposal.get("name", ""))
                )
        except Exception:
            pass
        result.finished_at = datetime.now(timezone.utc).isoformat()
        clear_progress()
        self._persist(result)
        self._log(result, learn=True)
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
