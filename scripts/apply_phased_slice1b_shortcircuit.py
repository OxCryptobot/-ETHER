"""Phase D: after tool_runtime score=1.0, skip generate — CQ multifile verify only."""
from __future__ import annotations
import ast
from pathlib import Path

tr = Path("core/tool_runtime.py")
tt = tr.read_text(encoding="utf-8")
old_cfr = '''def code_from_result(result):
    """Flatten final_code into a single artifact (markers if multi-file)."""
    files = result.final_code or {}
    if not files:
        return ""
    if len(files) == 1:
        return next(iter(files.values()))
    parts = []
    for rel, body in sorted(files.items()):
        parts.append("# file: " + rel + chr(10) + body)
    return (chr(10) + chr(10)).join(parts)'''
new_cfr = '''def code_from_result(result):
    """Flatten final_code into a single artifact (always # file: markers)."""
    files = result.final_code or {}
    if not files:
        return ""
    parts = []
    for rel, body in sorted(files.items()):
        parts.append("# file: " + rel + chr(10) + body)
    return (chr(10) + chr(10)).join(parts)'''
if "always # file: markers" in tt:
    print("code_from_result: already")
elif old_cfr in tt:
    tt = tt.replace(old_cfr, new_cfr, 1)
    ast.parse(tt)
    tr.write_text(tt, encoding="utf-8")
    print("code_from_result: markers always")
else:
    print("WARN: code_from_result form mismatch")

p = Path("core/pipeline.py")
t = p.read_text(encoding="utf-8")
if "multifile_verify exit=" in t:
    print("pipeline short-circuit: already")
else:
    marker = "            # Agent loop path (ETHER_AGENT_LOOP=1). Draws several candidates at"
    if marker not in t:
        raise SystemExit("agent loop marker not found")
    insert = '''            _tool_path_complete = False
            # Phase D: tool_runtime already passed project pytest — re-verify
            # only via Clear Quartz multifile, skip Rose Quartz generate.
            if tool_runtime_done and generated:
                from core.schemas import ClearQuartzRequest, ClearQuartzResponse
                t3 = time.perf_counter()
                write_progress(tid, objective, "sandbox")
                files = dict(getattr(result, "_tool_files", None) or {})
                fixture_env = (os.getenv("ETHER_TOOL_RUNTIME_FIXTURE") or "").strip()
                sand_req = Envelope(
                    task_id=task_id,
                    target_gem="clear-quartz",
                    payload=ClearQuartzRequest(
                        code=generated,
                        objective=objective,
                        prepare_code=False,
                        test_args=["tests"],
                        files=files,
                        fixture_root=fixture_env or None,
                    ),
                    timeout_seconds=timeout,
                )
                sand_res = self.registry.execute(sand_req)
                self.orchestrator.process_response(sand_req, sand_res)
                if sand_res.error or not isinstance(sand_res.payload, ClearQuartzResponse):
                    result.degraded.append("tool_runtime_cq_verify_failed")
                    result.stages.append(
                        StageResult(
                            stage="sandbox",
                            success=False,
                            detail=f"cq verify error: {(sand_res.error.message if sand_res.error else 'bad payload')[:160]}",
                            duration_ms=(time.perf_counter() - t3) * 1000,
                        )
                    )
                else:
                    sand_payload = sand_res.payload
                    result.sandbox = sand_payload
                    scores = compute_scores(sand_payload)
                    result.confidence = scores["confidence"]
                    result.execution_score = scores["execution_score"]
                    result.verification_score = scores["verification_score"]
                    cq_ok = sand_payload.exit_code == 0
                    result.stages.append(
                        StageResult(
                            stage="sandbox",
                            success=cq_ok,
                            detail=(
                                f"multifile_verify exit={sand_payload.exit_code} "
                                f"tests={sand_payload.tests_passed}/{sand_payload.total_tests} "
                                f"flags={sand_payload.security_flags[:3]}"
                            )[:300],
                            duration_ms=(time.perf_counter() - t3) * 1000,
                        )
                    )
                    if cq_ok:
                        result.repo_oracle_ok = True
                        result.verification_score = max(float(result.verification_score or 0), 1.0)
                        result.execution_score = max(float(result.execution_score or 0), 1.0)
                        result.first_compile_ok = True
                    else:
                        result.repo_oracle_ok = False
                        result.degraded.append("cq_multifile_verify_failed_after_tool_runtime")
                _tool_path_complete = True

            '''
    t = t.replace(marker, insert + marker, 1)
    old_while = "            while attempt < max_attempts:"
    if old_while not in t:
        raise SystemExit("while attempt not found")
    t = t.replace(old_while, "            while attempt < max_attempts and not _tool_path_complete:", 1)
    ast.parse(t)
    p.write_text(t, encoding="utf-8")
    print("pipeline: short-circuit written", len(t))

print("done")
