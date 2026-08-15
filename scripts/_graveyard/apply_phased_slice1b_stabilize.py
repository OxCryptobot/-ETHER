"""Phase D stabilize: local workspace_kept, multifile not a security flag, skip re-verify."""
from __future__ import annotations
import ast, re
from pathlib import Path

cp = Path("core/confidence.py")
ct = cp.read_text(encoding="utf-8")
old = '    security_flags = [f for f in resp.security_flags if not f.startswith("sandbox_fallback:")]'
new = '''    security_flags = [
        f for f in resp.security_flags
        if not f.startswith("sandbox_fallback:")
        and not f.startswith("multifile:")
    ]'''
if "not f.startswith(\"multifile:\")" in ct:
    print("confidence: already")
elif old in ct:
    cp.write_text(ct.replace(old, new, 1), encoding="utf-8")
    print("confidence: strip multifile")
else:
    print("WARN: confidence filter not found")

p = Path("core/pipeline.py")
t = p.read_text(encoding="utf-8")

if "workspace_kept = None" not in t:
    t = t.replace(
        "            tool_runtime_done = False\n",
        "            tool_runtime_done = False\n            tool_files = {}\n            workspace_kept = None\n",
        1,
    )
    print("init locals")
else:
    print("init: already")

if 'workspace_kept = getattr(tr, "workspace_kept"' not in t:
    t = t.replace(
        "                        tool_files = dict(tr.final_code or {})\n",
        "                        tool_files = dict(tr.final_code or {})\n"
        '                        workspace_kept = getattr(tr, "workspace_kept", None)\n',
        1,
    )
    print("capture workspace_kept")
else:
    print("capture: already")

m = re.search(
    r"if tool_runtime_done and generated:.*?_tool_path_complete = True",
    t,
    re.DOTALL,
)
if not m:
    raise SystemExit("short-circuit not found")
if "verify_exception:" in m.group(0) and "no_kept_dir" in m.group(0):
    print("short-circuit: already stabilized")
else:
    new_sc = r'''if tool_runtime_done and generated:
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
                        from core.schemas import ClearQuartzRequest, ClearQuartzResponse
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
                _tool_path_complete = True'''
    t = t[: m.start()] + new_sc + t[m.end() :]
    print("short-circuit: stabilized")

old = """            if loop_runner_enabled():
                _out = LoopRunner(registry=self.registry).run_verify(
                    VerificationContext("""
new = """            if _tool_path_complete:
                exit_code = 0 if result.repo_oracle_ok else 1
                total_tests = (
                    int(getattr(result.sandbox, "total_tests", 0) or 0) if result.sandbox else 0
                )
            elif loop_runner_enabled():
                _out = LoopRunner(registry=self.registry).run_verify(
                    VerificationContext("""
if "if _tool_path_complete:" in t and "exit_code = 0 if result.repo_oracle_ok" in t:
    print("skip re-verify: already")
elif old in t:
    t = t.replace(old, new, 1)
    print("skip re-verify: applied")
else:
    print("WARN: verify block not found")

ast.parse(t)
p.write_text(t, encoding="utf-8")
print("done", len(t))
