"""Phase D: CQ re-verify on the SAME tool workspace (no file-map drift)."""
from __future__ import annotations
import ast, re
from pathlib import Path

tr = Path("core/tool_runtime.py")
tt = tr.read_text(encoding="utf-8")
if "workspace_kept" not in tt:
    tt = tt.replace(
        """@dataclass
class RuntimeResult:
    ok: bool
    score: float
    steps: List[StepRecord] = field(default_factory=list)
    final_code: Dict[str, str] = field(default_factory=dict)
    error: str = ""
    reason: str = ""
    n_steps: int = 0
    elapsed_s: float = 0.0""",
        """@dataclass
class RuntimeResult:
    ok: bool
    score: float
    steps: List[StepRecord] = field(default_factory=list)
    final_code: Dict[str, str] = field(default_factory=dict)
    error: str = ""
    reason: str = ""
    n_steps: int = 0
    elapsed_s: float = 0.0
    workspace_kept: Optional[str] = None""",
        1,
    )
    print("RuntimeResult: workspace_kept field")
else:
    print("RuntimeResult: already")

old_ok = """                    if obs.get("ok"):
                        last_ok = True
                        return RuntimeResult(
                            ok=True,
                            score=sc,
                            steps=list(self.steps),
                            final_code=self._snapshot_code(),
                            reason="tests passed",
                            n_steps=len(self.steps),
                            elapsed_s=time.perf_counter() - t0,
                        )"""
new_ok = """                    if obs.get("ok"):
                        last_ok = True
                        snap = self._snapshot_code()
                        kept = str(self.workspace) if self.workspace is not None else None
                        self.workspace = None  # caller owns cleanup
                        return RuntimeResult(
                            ok=True,
                            score=sc,
                            steps=list(self.steps),
                            final_code=snap,
                            reason="tests passed",
                            n_steps=len(self.steps),
                            elapsed_s=time.perf_counter() - t0,
                            workspace_kept=kept,
                        )"""
if "workspace_kept=kept" in tt:
    print("ok return: already")
elif old_ok in tt:
    tt = tt.replace(old_ok, new_ok, 1)
    print("ok return: keep workspace")
else:
    raise SystemExit("ok return block not found")
ast.parse(tt)
tr.write_text(tt, encoding="utf-8")

p = Path("core/pipeline.py")
t = p.read_text(encoding="utf-8")

if "_workspace_kept" not in t:
    if "tool_files = dict(tr.final_code or {})" in t:
        t = t.replace(
            "tool_files = dict(tr.final_code or {})\n",
            "tool_files = dict(tr.final_code or {})\n"
            "                        try:\n"
            "                            object.__setattr__(result, \"_workspace_kept\", getattr(tr, \"workspace_kept\", None))\n"
            "                        except Exception:\n"
            "                            result.__dict__[\"_workspace_kept\"] = getattr(tr, \"workspace_kept\", None)\n",
            1,
        )
        print("stashed workspace_kept")
    else:
        print("WARN: tool_files line missing")
else:
    print("workspace_kept stash: already")

m = re.search(
    r"if tool_runtime_done and generated:.*?_tool_path_complete = True",
    t,
    re.DOTALL,
)
if not m:
    raise SystemExit("short-circuit block not found — run shortcircuit apply first")
if "workspace_verify exit=" in m.group(0):
    print("workspace verify: already")
else:
    new_sc = '''if tool_runtime_done and generated:
                from core.repo_oracle import run_project_pytest
                from pathlib import Path as _Path
                t3 = time.perf_counter()
                write_progress(tid, objective, "sandbox")
                kept = getattr(result, "_workspace_kept", None)
                cq_ok = False
                detail = ""
                try:
                    if kept and _Path(str(kept)).is_dir():
                        pr = run_project_pytest(
                            _Path(str(kept)),
                            test_args=["tests"],
                            timeout=max(30, int(timeout)),
                        )
                        cq_ok = bool(pr.get("ok"))
                        score = float(pr.get("score") or 0.0)
                        result.verification_score = 1.0 if cq_ok else score
                        result.execution_score = result.verification_score
                        detail = (
                            f"workspace_verify exit={pr.get('returncode')} "
                            f"score={score} ok={cq_ok} "
                            f"tail={(pr.get('stdout') or '')[-300]!r}"
                        )
                    else:
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
                        if sand_res.error or not isinstance(
                            sand_res.payload, ClearQuartzResponse
                        ):
                            detail = f"cq error: {sand_res.error}"
                            cq_ok = False
                        else:
                            sp = sand_res.payload
                            result.sandbox = sp
                            scores = compute_scores(sp)
                            result.confidence = scores["confidence"]
                            result.execution_score = scores["execution_score"]
                            result.verification_score = scores["verification_score"]
                            cq_ok = sp.exit_code == 0
                            detail = (
                                f"multifile_verify exit={sp.exit_code} "
                                f"tests={sp.tests_passed}/{sp.total_tests} "
                                f"files={len(files)}"
                            )
                finally:
                    kept2 = getattr(result, "_workspace_kept", None) or kept
                    if kept2:
                        import shutil as _sh
                        _sh.rmtree(str(kept2), ignore_errors=True)
                result.stages.append(
                    StageResult(
                        stage="sandbox",
                        success=cq_ok,
                        detail=detail[:500],
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
    print("workspace verify path written")

ast.parse(t)
p.write_text(t, encoding="utf-8")
print("done", len(t))
