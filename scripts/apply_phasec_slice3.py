"""Apply Phase C slice 3: tool_runtime entry + pipeline wire.

Run from repo root:
  .\.venv\Scripts\python.exe scripts\apply_phasec_slice3.py
"""
from __future__ import annotations

import ast
from pathlib import Path

# --- 1. tool_runtime.py ---
tr = Path("core/tool_runtime.py")
tt = tr.read_text(encoding="utf-8")
if "def run_if_enabled" not in tt:
    addon = """

def run_if_enabled(
    objective: str,
    *,
    decide_fn=None,
    fixture_root=None,
    max_steps=None,
    timeout_s=None,
):
    \"\"\"Phase C slice 3 entry — run tool runtime when gated on, else None.\"\"\"
    import os
    from pathlib import Path as _P

    if not tool_runtime_enabled():
        return None
    root = fixture_root
    if root is None:
        raw = (
            (os.getenv("ETHER_TOOL_RUNTIME_FIXTURE") or "").strip()
            or (os.getenv("ETHER_REPO_ORACLE_FIXTURE") or "").strip()
        )
        if not raw:
            return None
        root = _P(raw)
    root = _P(root)
    if not root.is_dir():
        return RuntimeResult(ok=False, score=0.0, error=f"fixture not found: {root}")
    steps = max_steps
    if steps is None:
        try:
            steps = int(os.getenv("ETHER_TOOL_RUNTIME_STEPS") or "8")
        except ValueError:
            steps = 8
    wall = timeout_s
    if wall is None:
        try:
            wall = float(os.getenv("ETHER_TOOL_RUNTIME_SECONDS") or "180")
        except ValueError:
            wall = 180.0
    decide = decide_fn if decide_fn is not None else make_llm_decide_fn()
    rt = ToolRuntime(
        fixture_root=root,
        decide_fn=decide,
        max_steps=steps,
        timeout_s=wall,
    )
    return rt.run(objective)


def code_from_result(result):
    \"\"\"Flatten final_code into a single artifact (markers if multi-file).\"\"\"
    files = result.final_code or {}
    if not files:
        return ""
    if len(files) == 1:
        return next(iter(files.values()))
    parts = []
    for rel, body in sorted(files.items()):
        parts.append("# file: " + rel + chr(10) + body)
    return (chr(10) + chr(10)).join(parts)
"""
    tr.write_text(tt.rstrip() + "\n" + addon + "\n", encoding="utf-8")
    print("tool_runtime: appended run_if_enabled")
else:
    print("tool_runtime: already has run_if_enabled")

# --- 2. pipeline.py ---
p = Path("core/pipeline.py")
t = p.read_text(encoding="utf-8")
if "tool_runtime_done" in t and "run_if_enabled" in t:
    print("pipeline: already wired")
    raise SystemExit(0)

needle = """            # Agent loop path (ETHER_AGENT_LOOP=1). Draws several candidates at
            # varied temperature, scores each WITHOUT a holdout, repairs against
            # what actually ran, and returns the best — never overwriting a
            # better earlier attempt, which is what the fixed two-shot retry did.
            loop_result = None
            if self._agent_loop_enabled():"""

block = """            # Phase C tool-runtime path (ETHER_TOOL_RUNTIME=1 + fixture).
            tool_runtime_done = False
            try:
                from core.tool_runtime import (
                    code_from_result,
                    run_if_enabled,
                    tool_runtime_enabled,
                )
                if tool_runtime_enabled():
                    tr_t0 = time.perf_counter()
                    tr = run_if_enabled(objective)
                    if tr is not None:
                        generated = code_from_result(tr) or ""
                        result.generated_code = generated
                        result.strategy = "tool_runtime"
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

            # Agent loop path (ETHER_AGENT_LOOP=1). Draws several candidates at
            # varied temperature, scores each WITHOUT a holdout, repairs against
            # what actually ran, and returns the best — never overwriting a
            # better earlier attempt, which is what the fixed two-shot retry did.
            loop_result = None
            if self._agent_loop_enabled():"""

if needle not in t:
    raise SystemExit("needle not found — pipeline layout changed")
t = t.replace(needle, block, 1)

old2 = """                if loop_result is not None and generated:
                    # The agent loop already generated, verified and selected.
                    # Fall through to sandbox + audit without re-drawing.
                    pass"""
new2 = """                if tool_runtime_done and generated:
                    pass
                elif loop_result is not None and generated:
                    # The agent loop already generated, verified and selected.
                    # Fall through to sandbox + audit without re-drawing.
                    pass"""
if old2 not in t:
    raise SystemExit("old2 not found")
t = t.replace(old2, new2, 1)

old3 = """                    if loop_result is not None and generated:
                        # The agent loop drew, verified and selected already.
                        # Record its prompts for the leak guard and skip the
                        # legacy single-shot generation entirely.
                        for _a in loop_result.attempts:
                            _p = getattr(_a, "prompt", "")
                            if _p:
                                sent_prompts.append(_p)
                        code_res = None
                        raise _LoopAlreadyGenerated"""
new3 = """                    if tool_runtime_done and generated:
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
                        raise _LoopAlreadyGenerated"""
if old3 not in t:
    raise SystemExit("old3 not found")
t = t.replace(old3, new3, 1)

ast.parse(t)
p.write_text(t, encoding="utf-8")
print("pipeline: wired OK", len(t))
