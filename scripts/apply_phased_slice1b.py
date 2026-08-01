"""Phase D slice 1b — multifile Clear Quartz + drop pipeline bypass.

Run: python scripts/apply_phased_slice1b.py
"""
from __future__ import annotations

import ast
from pathlib import Path

# --- schemas ---
sp = Path("core/schemas.py")
st = sp.read_text(encoding="utf-8")
if "files: Dict[str, str]" not in st:
    old = '''class ClearQuartzRequest(BaseModel):
    code: str
    language: Literal["python", "javascript", "rust", "go"] = "python"
    test_cases: List[str] = Field(default_factory=list)
    sandbox_profile: Literal["fast", "strict"] = "fast"
    # The originating objective. test_synth derives its only genuinely
    # falsifiable assertions by matching `name(args) == value` against this;
    # the sandbox previously hardcoded objective="" so that branch could never
    # fire and every synthesized assert was a tautology.
    objective: str = ""'''
    new = '''class ClearQuartzRequest(BaseModel):
    code: str = ""
    language: Literal["python", "javascript", "rust", "go"] = "python"
    test_cases: List[str] = Field(default_factory=list)
    sandbox_profile: Literal["fast", "strict"] = "fast"
    # The originating objective. test_synth derives its only genuinely
    # falsifiable assertions by matching `name(args) == value` against this;
    # the sandbox previously hardcoded objective="" so that branch could never
    # fire and every synthesized assert was a tautology.
    objective: str = ""
    # Phase D slice 1b — multifile workspace (relative path → content).
    files: Dict[str, str] = Field(default_factory=dict)
    test_args: List[str] = Field(default_factory=list)
    fixture_root: Optional[str] = None
    prepare_code: bool = True'''
    if old not in st:
        raise SystemExit("schemas: ClearQuartzRequest block not found")
    st = st.replace(old, new, 1)
    ast.parse(st)
    sp.write_text(st, encoding="utf-8")
    print("schemas: multifile fields")
else:
    print("schemas: already")

# --- clear quartz ---
cp = Path("gems/clear_quartz/sandbox.py")
ct = cp.read_text(encoding="utf-8")
if "_execute_multifile" not in ct:
    old = '''        payload = request.payload
        start = time.perf_counter()
        code = payload.code
        # The objective is what makes test_synth able to derive a falsifiable
        # assertion (`name(args) == value`). This used to be hardcoded to "",
        # so that branch could never fire in production and every synthesized
        # assertion was a tautology.
        objective = str(getattr(payload, "objective", "") or "")
        if self._prep_enabled(payload):'''
    new = '''        payload = request.payload
        start = time.perf_counter()
        code = payload.code or ""
        # The objective is what makes test_synth able to derive a falsifiable
        # assertion (`name(args) == value`). This used to be hardcoded to "",
        # so that branch could never fire in production and every synthesized
        # assertion was a tautology.
        objective = str(getattr(payload, "objective", "") or "")

        # Phase D slice 1b — multifile / project-pytest path
        files = dict(getattr(payload, "files", None) or {})
        if not files and "# file:" in code:
            try:
                from core.multifile import extract_file_blocks
                files = extract_file_blocks(code)
            except Exception:
                files = {}
        if files:
            return self._execute_multifile(request, payload, files, start)

        if self._prep_enabled(payload):'''
    if old not in ct:
        raise SystemExit("clear_quartz: execute start not found")
    ct = ct.replace(old, new, 1)

    method = '''
    def _execute_multifile(
        self,
        request: Envelope,
        payload: ClearQuartzRequest,
        files: dict,
        start: float,
    ) -> ResponseEnvelope:
        """Seed staging workspace and run project pytest (shared with repo_oracle).

        Clear Quartz remains the truth container: observe only, no code mutation.
        """
        from pathlib import Path as _P

        joined = "\\n\\n".join(f"# file: {k}\\n{v}" for k, v in sorted(files.items()))
        security_flags = self._static_analysis(joined)

        fixture_raw = (
            getattr(payload, "fixture_root", None)
            or (os.getenv("ETHER_TOOL_RUNTIME_FIXTURE") or "").strip()
            or (os.getenv("ETHER_REPO_ORACLE_FIXTURE") or "").strip()
            or ""
        )
        fixture_root = _P(fixture_raw) if fixture_raw else None
        if fixture_root is not None and not fixture_root.is_dir():
            fixture_root = None

        test_args = list(getattr(payload, "test_args", None) or []) or ["tests"]
        timeout = int(getattr(request, "timeout_seconds", None) or 60)

        try:
            from core.repo_oracle import score_repo_edit

            result = score_repo_edit(
                files,
                fixture_root=fixture_root,
                test_args=test_args,
                timeout=timeout,
                cleanup=True,
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                error=GemError(
                    type=GemErrorType.RUNTIME,
                    message=f"multifile sandbox: {type(e).__name__}: {e}"[:300],
                    recoverable=True,
                ),
            )

        execution_time = time.perf_counter() - start
        ok = bool(result.get("ok"))
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        m_pass = re.search(r"(\\d+)\\s+passed", stdout + "\\n" + stderr)
        m_fail = re.search(r"(\\d+)\\s+failed", stdout + "\\n" + stderr)
        passed = int(m_pass.group(1)) if m_pass else 0
        failed = int(m_fail.group(1)) if m_fail else 0
        if passed or failed:
            total_tests = passed + failed
            tests_passed = passed
        elif ok:
            total_tests, tests_passed = 1, 1
        else:
            total_tests, tests_passed = 1, 0

        backend = sandbox_backend()
        flags = list(security_flags)
        flags.append("multifile:project_pytest")
        if backend == "local":
            flags.append("sandbox_fallback:local")

        return ResponseEnvelope(
            task_id=request.task_id,
            source_gem="clear-quartz",
            payload=ClearQuartzResponse(
                stdout=stdout[-4000:],
                stderr=(stderr or str(result.get("error") or ""))[-2000:],
                exit_code=0 if ok else int(result.get("returncode") or 1),
                total_tests=total_tests,
                tests_passed=tests_passed,
                security_flags=flags,
                execution_time=round(execution_time, 3),
                static_analysis_score=0.0 if security_flags else 1.0,
            ),
        )

'''
    anchor = "    @staticmethod\n    def _prep_enabled(payload: ClearQuartzRequest) -> bool:"
    if anchor not in ct:
        raise SystemExit("clear_quartz: prep_enabled anchor missing")
    ct = ct.replace(anchor, method + anchor, 1)
    ast.parse(ct)
    cp.write_text(ct, encoding="utf-8")
    print("clear_quartz: multifile path")
else:
    print("clear_quartz: already")

# --- pipeline ---
pp = Path("core/pipeline.py")
pt = pp.read_text(encoding="utf-8")
changed = False
if "bypassed: tool_runtime already verified" in pt:
    old = """                t3 = time.perf_counter()
                if tool_runtime_done and generated:
                    # Trust tool-runtime project pytest; skip Clear Quartz.
                    result.stages.append(
                        StageResult(
                            stage="sandbox",
                            success=True,
                            detail="bypassed: tool_runtime already verified via project pytest",
                            duration_ms=(time.perf_counter() - t3) * 1000,
                        )
                    )
                    result.stages.append(
                        StageResult(
                            stage="repo_oracle",
                            success=True,
                            detail=f"trusted tool_runtime score={result.verification_score}",
                        )
                    )
                    ok = True
                    break
                write_progress(tid, objective, "sandbox")
"""
    new = """                t3 = time.perf_counter()
                write_progress(tid, objective, "sandbox")
"""
    if old not in pt:
        raise SystemExit("pipeline: bypass block mismatch")
    pt = pt.replace(old, new, 1)
    print("pipeline: bypass removed")
    changed = True
else:
    print("pipeline: no bypass")

old_payload = "payload=ClearQuartzRequest(code=generated, objective=objective),"
new_payload = """payload=ClearQuartzRequest(
                        code=generated,
                        objective=objective,
                        prepare_code=not bool(tool_runtime_done),
                        test_args=["tests"],
                    ),"""
if old_payload in pt:
    pt = pt.replace(old_payload, new_payload, 1)
    print("pipeline: sand_req multifile-aware")
    changed = True
elif "prepare_code=not bool(tool_runtime_done)" in pt:
    print("pipeline: sand_req already")
else:
    print("WARN: sand_req not found")

if changed:
    ast.parse(pt)
    pp.write_text(pt, encoding="utf-8")
    print("pipeline: written", len(pt))

print("phaseD slice1b done")
