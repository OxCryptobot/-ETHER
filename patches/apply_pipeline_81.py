#!/usr/bin/env python3
"""One-shot local patcher for pipeline.py task 81 (idempotent)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "core" / "pipeline.py"
text = path.read_text(encoding="utf-8")
orig = text

if "from core.pipeline_select import select_strategy" not in text:
    text = text.replace(
        "from core.bench_guardian import is_frozen\n",
        "from core.bench_guardian import is_frozen\n"
        "from core.pipeline_select import select_strategy\n"
        "from core.pipeline_hooks import prepare_code_for_sandbox\n",
    )

text = text.replace(
    "strategy = self.policy.select() if learning_enabled() else \"default\"",
    "strategy = select_strategy(objective, self.policy) if learning_enabled() else \"default\"",
)

old = """                t3 = time.perf_counter()
                write_progress(tid, objective, \"sandbox\")
                sand_req = Envelope(
                    task_id=task_id,
                    target_gem=\"clear-quartz\",
                    payload=ClearQuartzRequest(code=generated),
                    timeout_seconds=timeout,
                )"""

new = """                t3 = time.perf_counter()
                write_progress(tid, objective, \"sandbox\")
                try:
                    generated, _prep = prepare_code_for_sandbox(generated, objective)
                    result.generated_code = generated
                except Exception:
                    pass
                sand_req = Envelope(
                    task_id=task_id,
                    target_gem=\"clear-quartz\",
                    payload=ClearQuartzRequest(code=generated),
                    timeout_seconds=timeout,
                )"""

if old in text and "prepare_code_for_sandbox(generated" not in text:
    text = text.replace(old, new)

if text != orig:
    path.write_text(text, encoding="utf-8")
    print("patched", path)
else:
    print("already patched or pattern mismatch")
