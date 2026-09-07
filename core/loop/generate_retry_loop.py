"""Generate/repair while-loop peeled off Pipeline.run."""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict

MAX_CODE_CHARS = 50_000


class _LoopAlreadyGenerated(Exception):
    """Control-flow: agent loop already produced the artifact."""


def run_generate_retry_loop(
    pipe: Any,
    result: Any,
    *,
    write_progress: Callable[..., None],
    repo_map_block: Callable[[], str],
    workspace_block: Callable[[], str],
    st: Dict[str, Any],
) -> Dict[str, Any]:
    from core.confidence import compute_scores
    from core.learning import arm_behaviour, strategy_prompt_addon
    from core.loop.generate_retry import first_prompt, retry_prompt
    from core.loop.gems_call import rose_complete, sandbox_execute
    from core.loop.pipeline_util import is_burst_model as _is_burst_model
    from core.loop.pipeline_util import looks_multifile as _looks_multifile
    from core.loop.stage_mark import skip_detail
    from core.pipeline import StageResult, _Attempt
    from core.pipeline_burst import decide_burst
    from core.pipeline_select import current_tier, select_strategy_with_context
    from core.repair import classify_stderr
    from core.schemas import ClearQuartzResponse, RoseQuartzResponse

    self = pipe
    attempt = int(st["attempt"])
    max_attempts = int(st["max_attempts"])
    _tool_path_complete = bool(st["_tool_path_complete"])
    generated = st.get("generated") or ""
    tool_runtime_done = bool(st.get("tool_runtime_done"))
    loop_result = st.get("loop_result")
    tid = st["tid"]
    objective = st["objective"]
    strategy = st["strategy"]
    strategy_hint = st.get("strategy_hint") or ""
    fail_kind = st.get("fail_kind") or ""
    last_err = st.get("last_err") or ""
    skip = st.get("skip") or set()
    timeout = int(st["timeout"])
    prefer_local = bool(st["prefer_local"])
    task_id = st["task_id"]
    sent_prompts = st["sent_prompts"]
    attempts = st["attempts"]
    tool_block = st.get("tool_block") or ""
    exp_block = st.get("exp_block")
    few_shot = st.get("few_shot")
    ok = bool(st.get("ok", False))

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
    st["attempt"] = attempt
    st["generated"] = generated
    st["strategy"] = strategy
    st["strategy_hint"] = strategy_hint
    st["fail_kind"] = fail_kind
    st["last_err"] = last_err
    st["ok"] = ok
    st["sent_prompts"] = sent_prompts
    st["attempts"] = attempts
    return st
