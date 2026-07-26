"""End-to-end pipeline — P0–P2 complete wiring."""

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
    started_at: str = ""
    finished_at: str = ""


def _looks_multifile(objective: str) -> bool:
    o = objective.lower()
    return bool(
        re.search(r"\b(class|module|package|refactor|file|project|codebase)\b", o)
        or ".py" in o
    )


class Pipeline:
    def __init__(self, registry: Optional[GemRegistry] = None):
        self.registry = registry or build_default_registry()
        self.orchestrator = Orchestrator()
        self.runs_dir = Path("memory/runs")
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.policy = BanditPolicy()

    def run(self, objective: str, prefer_local: bool = True, critique: bool = False) -> PipelineResult:
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
            result.stages.append(
                StageResult(
                    stage="plan",
                    success=True,
                    detail=f"{len(result.plan.steps)} steps tool={plan_res.payload.needs_tool}",
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )
            )

            # Mid-pipeline tool: generate / fabricate / run
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
            if tool_assist:
                t_ta = time.perf_counter()
                write_progress(tid, objective, "tool_assist")
                try:
                    from gems.grandidierite.registry import run_tool

                    fs = run_tool("few_shot_pack", {"query": objective, "top_k": 2})
                    if fs.get("ok") and isinstance(fs.get("result"), dict):
                        few_shot = fs["result"].get("block") or ""
                        result.few_shot_chars = len(few_shot)
                    if _looks_multifile(objective):
                        rm = run_tool("repo_map", {"max_files": 40})
                        if rm.get("ok"):
                            files = (rm.get("files") or [])[:15]
                            lines = [f["path"] + ": " + ", ".join(f.get("symbols") or []) for f in files]
                            repo_map_txt = "\n".join(lines)[:2500]
                    result.stages.append(
                        StageResult(
                            stage="tool_assist",
                            success=True,
                            detail=f"few_shot={result.few_shot_chars}c map={len(repo_map_txt)}c",
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
            last_err = ""
            strategy_hint = strategy_prompt_addon(strategy)

            while attempt < max_attempts:
                attempt += 1
                t2 = time.perf_counter()
                write_progress(tid, objective, "code" if attempt == 1 else "code_retry")
                if attempt == 1:
                    prompt = (
                        f"Write Python code for:\n{objective}\n\n"
                        f"Strategy: {strategy_hint}\n\n"
                        f"Plan:\n{result.plan.model_dump_json(indent=2)}\n\n"
                    )
                    if tool_block:
                        prompt += f"Tool output:\n{tool_block}\n\n"
                    if few_shot:
                        prompt += f"Few-shot success patterns:\n{few_shot}\n\n"
                    if repo_map_txt:
                        prompt += f"Repo map (symbols):\n{repo_map_txt}\n\n"
                    if context_block:
                        prompt += f"Relevant workspace context:\n{context_block}\n\n"
                    prompt += "Return only executable Python code, no markdown fences."
                else:
                    result.retries += 1
                    prompt = repair_prompt(objective, generated, last_err, strategy_hint)

                code_req = Envelope(
                    task_id=task_id,
                    target_gem="rose-quartz",
                    payload=RoseQuartzRequest(
                        messages=[ChatMessage(role="user", content=prompt)],
                        prefer_local=prefer_local,
                    ),
                )
                code_res = self.registry.execute(code_req)
                self.orchestrator.process_response(code_req, code_res)
                if code_res.error or not isinstance(code_res.payload, RoseQuartzResponse):
                    return self._fail(
                        result, "code", code_res.error.message if code_res.error else "code failed", t2
                    )
                generated = self._strip(code_res.payload.content)
                if len(generated) > MAX_CODE_CHARS:
                    return self._fail(result, "code", f"Generated code exceeds {MAX_CODE_CHARS} chars", t2)
                result.generated_code = generated
                result.stages.append(
                    StageResult(
                        stage="code" if attempt == 1 else "code_retry",
                        success=True,
                        detail=f"{len(generated)} chars strategy={strategy}",
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
                _ = classify_stderr(last_err)

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
            result.reward = compute_reward(
                exit_code=exit_code,
                confidence=result.confidence,
                audit_approved=audit_ok,
                retries=result.retries,
            )
            if learning_enabled():
                self.policy.update(strategy, result.reward)

            success = exit_code == 0
            record_outcome(success, error=None if success else (last_err or result.error))

            if not success:
                proposal = maybe_propose_fabricate()
                if proposal:
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
                    result.stages.append(
                        StageResult(stage="memory_save", success=True, detail="success_pattern")
                    )
                except Exception:
                    pass

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
            exit_code=1, confidence=0.0, audit_approved=False, retries=result.retries
        )
        if learning_enabled() and result.strategy:
            try:
                self.policy.update(result.strategy, result.reward)
            except Exception:
                pass
        try:
            record_outcome(False, error=msg)
            proposal = maybe_propose_fabricate()
            if proposal:
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
