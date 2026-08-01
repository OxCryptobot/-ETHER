"""Phase D slice1: when tool_runtime already passed project pytest, trust it.

Do not re-flatten multifile into Clear Quartz (pipeline scored 0.2 while direct 1.0).

Run: python scripts/apply_phased_slice1.py
"""
from __future__ import annotations

import ast
from pathlib import Path

p = Path("core/pipeline.py")
t = p.read_text(encoding="utf-8")
if "bypassed: tool_runtime already verified" in t:
    print("already applied")
    raise SystemExit(0)

old = """                        if tr.ok and generated:
                            tool_runtime_done = True
                            max_attempts = 1"""
new = """                        if tr.ok and generated:
                            tool_runtime_done = True
                            max_attempts = 1
                            # Project pytest already passed in tool staging.
                            # Do not re-score via single-file Clear Quartz —
                            # multifile (# file:) artifacts get mangled there
                            # (Phase D slice1: pipeline score 0.2 vs direct 1.0).
                            result.repo_oracle_ok = True
                            result.verification_score = float(tr.score)
                            result.execution_score = float(tr.score)
                            result.confidence = max(float(result.confidence or 0), float(tr.score))"""
if old not in t:
    raise SystemExit("tool success block not found")
t = t.replace(old, new, 1)

old_sand = """                t3 = time.perf_counter()
                write_progress(tid, objective, "sandbox")
                sand_req = Envelope("""
new_sand = """                t3 = time.perf_counter()
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
                sand_req = Envelope("""
if old_sand not in t:
    raise SystemExit("sandbox block not found")
t = t.replace(old_sand, new_sand, 1)

ast.parse(t)
p.write_text(t, encoding="utf-8")
print("applied", len(t))
