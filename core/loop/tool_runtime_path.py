"""Tool-runtime path peeled off Pipeline.run (Phase C/D + 984s hang terminal)."""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, Optional, Tuple


def run_tool_runtime_path(
    pipe: Any,
    result: Any,
    *,
    objective: str,
    timeout: int,
    skip: set,
    tid: str,
    task_id: Any,
    attempts: list,
    generated: str,
    write_progress: Callable[..., None],
) -> Dict[str, Any]:
    from core.loop.gems_call import sandbox_execute
    from core.loop.stage_mark import skip_detail
    from core.pipeline import StageResult
    from core.schemas import ClearQuartzResponse

    tool_runtime_done = False
    _tool_path_complete = False
    max_attempts = None
    tool_files: dict = {}
    workspace_kept = None

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
        return {
            "generated": generated,
            "tool_runtime_done": tool_runtime_done,
            "tool_path_complete": False,
            "max_attempts": None,
            "fail": pipe._fail(
                result,
                "tool_runtime",
                "tool_runtime_failed_terminal",
                time.perf_counter(),
                attempts,
            ),
        }

    _tool_path_complete = False
    # Phase D: tool_runtime already passed project pytest — re-verify
    # only via Clear Quartz multifile, skip Rose Quartz generate.
    if tool_runtime_done and generated:
        from core.repo_oracle import run_project_pytest
        from pathlib import Path as _Path
        import shutil as _sh
        t3 = time.perf_counter()
        write_progress(
            tid,
            objective,
            "sandbox",
            detail=skip_detail(skip, "sandbox"),
        )
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
                sand_req, sand_res = sandbox_execute(
                    pipe.registry,
                    task_id=task_id,
                    generated=generated or "",
                    objective=objective,
                    timeout=timeout,
                    files=files,
                    prepare_code=False,
                    fixture_root=fixture_env or None,
                )
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

    return {
        "generated": generated,
        "tool_runtime_done": tool_runtime_done,
        "tool_path_complete": _tool_path_complete,
        "max_attempts": max_attempts,
        "fail": None,
    }
