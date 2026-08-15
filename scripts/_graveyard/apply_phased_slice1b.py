"""Phase D slice 1b — multifile Clear Quartz + drop pipeline bypass.

Run: python scripts/apply_phased_slice1b.py
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- schemas ---
sp = Path("core/schemas.py")
st = sp.read_text(encoding="utf-8")
if "files: Dict[str, str]" not in st:
    old = (
        'class ClearQuartzRequest(BaseModel):\n'
        '    code: str\n'
        '    language: Literal["python", "javascript", "rust", "go"] = "python"\n'
        '    test_cases: List[str] = Field(default_factory=list)\n'
        '    sandbox_profile: Literal["fast", "strict"] = "fast"\n'
        '    # The originating objective. test_synth derives its only genuinely\n'
        '    # falsifiable assertions by matching `name(args) == value` against this;\n'
        '    # the sandbox previously hardcoded objective="" so that branch could never\n'
        '    # fire and every synthesized assert was a tautology.\n'
        '    objective: str = ""'
    )
    new = (
        'class ClearQuartzRequest(BaseModel):\n'
        '    code: str = ""\n'
        '    language: Literal["python", "javascript", "rust", "go"] = "python"\n'
        '    test_cases: List[str] = Field(default_factory=list)\n'
        '    sandbox_profile: Literal["fast", "strict"] = "fast"\n'
        '    # The originating objective. test_synth derives its only genuinely\n'
        '    # falsifiable assertions by matching `name(args) == value` against this;\n'
        '    # the sandbox previously hardcoded objective="" so that branch could never\n'
        '    # fire and every synthesized assert was a tautology.\n'
        '    objective: str = ""\n'
        '    # Phase D slice 1b \u2014 multifile workspace.\n'
        '    files: Dict[str, str] = Field(default_factory=dict)\n'
        '    test_args: List[str] = Field(default_factory=list)\n'
        '    fixture_root: Optional[str] = None\n'
        '    prepare_code: bool = True'
    )
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
    old = (
        '        payload = request.payload\n'
        '        start = time.perf_counter()\n'
        '        code = payload.code\n'
        '        # The objective is what makes test_synth able to derive a falsifiable\n'
        '        # assertion (`name(args) == value`). This used to be hardcoded to "",\n'
        '        # so that branch could never fire in production and every synthesized\n'
        '        # assertion was a tautology.\n'
        '        objective = str(getattr(payload, "objective", "") or "")\n'
        '        if self._prep_enabled(payload):'
    )
    new = (
        '        payload = request.payload\n'
        '        start = time.perf_counter()\n'
        '        code = payload.code or ""\n'
        '        # The objective is what makes test_synth able to derive a falsifiable\n'
        '        # assertion (`name(args) == value`). This used to be hardcoded to "",\n'
        '        # so that branch could never fire in production and every synthesized\n'
        '        # assertion was a tautology.\n'
        '        objective = str(getattr(payload, "objective", "") or "")\n'
        '\n'
        '        # Phase D slice 1b \u2014 multifile / project-pytest path\n'
        '        files = dict(getattr(payload, "files", None) or {})\n'
        '        if not files and "# file:" in code:\n'
        '            try:\n'
        '                from core.multifile import extract_file_blocks\n'
        '                files = extract_file_blocks(code)\n'
        '            except Exception:\n'
        '                files = {}\n'
        '        if files:\n'
        '            return self._execute_multifile(request, payload, files, start)\n'
        '\n'
        '        if self._prep_enabled(payload):'
    )
    if old not in ct:
        raise SystemExit("clear_quartz: execute start not found")
    ct = ct.replace(old, new, 1)
    snip = (ROOT / "_cq_multifile_snip.py").read_text(encoding="utf-8")
    if not snip.lstrip().startswith("def _execute_multifile"):
        raise SystemExit("snippet missing _execute_multifile")
    anchor = "    @staticmethod\n    def _prep_enabled(payload: ClearQuartzRequest) -> bool:"
    if anchor not in ct:
        raise SystemExit("clear_quartz: prep_enabled anchor missing")
    ct = ct.replace(anchor, snip + anchor, 1)
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
    old = (
        '                t3 = time.perf_counter()\n'
        '                if tool_runtime_done and generated:\n'
        '                    # Trust tool-runtime project pytest; skip Clear Quartz.\n'
        '                    result.stages.append(\n'
        '                        StageResult(\n'
        '                            stage="sandbox",\n'
        '                            success=True,\n'
        '                            detail="bypassed: tool_runtime already verified via project pytest",\n'
        '                            duration_ms=(time.perf_counter() - t3) * 1000,\n'
        '                        )\n'
        '                    )\n'
        '                    result.stages.append(\n'
        '                        StageResult(\n'
        '                            stage="repo_oracle",\n'
        '                            success=True,\n'
        '                            detail=f"trusted tool_runtime score={result.verification_score}",\n'
        '                        )\n'
        '                    )\n'
        '                    ok = True\n'
        '                    break\n'
        '                write_progress(tid, objective, "sandbox")\n'
    )
    new = (
        '                t3 = time.perf_counter()\n'
        '                write_progress(tid, objective, "sandbox")\n'
    )
    if old not in pt:
        raise SystemExit("pipeline: bypass block mismatch")
    pt = pt.replace(old, new, 1)
    print("pipeline: bypass removed")
    changed = True
else:
    print("pipeline: no bypass")

old_payload = "payload=ClearQuartzRequest(code=generated, objective=objective),"
new_payload = (
    "payload=ClearQuartzRequest(\n"
    "                        code=generated,\n"
    "                        objective=objective,\n"
    "                        prepare_code=not bool(tool_runtime_done),\n"
    "                        test_args=[\"tests\"],\n"
    "                    ),"
)
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
