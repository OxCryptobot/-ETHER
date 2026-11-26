"""Phase D slice1b fix: arm tool_runtime reliably + pass files to CQ + diagnostics."""
from __future__ import annotations
import ast, re
from pathlib import Path

p = Path("core/pipeline.py")
t = p.read_text(encoding="utf-8")

m = re.search(
    r"if tool_runtime_enabled\(\):.*?(?=\n            except Exception as e:)",
    t,
    re.DOTALL,
)
if not m:
    raise SystemExit("tool_runtime block not found")
if "tool_runtime_skipped:no_result" not in m.group(0):
    new_block = '''if tool_runtime_enabled():
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
                        try:
                            setattr(result, "_tool_files", dict(tr.final_code or {}))
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
'''
    t = t[: m.start()] + new_block + t[m.end() :]
    print("tool block: replaced")
else:
    print("tool block: already")

old = """                    result.strategy = strategy
                    result.strategies.append(strategy)
                    strategy_hint = strategy_prompt_addon(strategy)
                behaviour = arm_behaviour(strategy)"""
new = """                    if not tool_runtime_done:
                        result.strategy = strategy
                        result.strategies.append(strategy)
                        strategy_hint = strategy_prompt_addon(strategy)
                behaviour = arm_behaviour(strategy)"""
if old in t and "if not tool_runtime_done:" not in t:
    t = t.replace(old, new, 1)
    print("strategy lock: applied")
elif "if not tool_runtime_done:" in t:
    print("strategy lock: already")
else:
    print("WARN: strategy overwrite site not found")

if 'files=dict(getattr(result, "_tool_files"' not in t:
    old_cq = "payload=ClearQuartzRequest(code=generated, objective=objective),"
    new_cq = """payload=ClearQuartzRequest(
                        code=generated,
                        objective=objective,
                        prepare_code=not bool(tool_runtime_done),
                        test_args=["tests"],
                        files=dict(getattr(result, "_tool_files", None) or {}),
                    ),"""
    if old_cq in t:
        t = t.replace(old_cq, new_cq, 1)
        print("cq files: single-line form")
    elif "prepare_code=not bool(tool_runtime_done)" in t and "files=dict" not in t:
        t = t.replace(
            'prepare_code=not bool(tool_runtime_done),\n                        test_args=["tests"],',
            'prepare_code=not bool(tool_runtime_done),\n                        test_args=["tests"],\n                        files=dict(getattr(result, "_tool_files", None) or {}),',
            1,
        )
        print("cq files: inserted")
    else:
        print("WARN: cq payload not patched")
else:
    print("cq files: already")

ast.parse(t)
p.write_text(t, encoding="utf-8")
print("pipeline written", len(t))
print("done")
