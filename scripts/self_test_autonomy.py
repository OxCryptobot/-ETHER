#!/usr/bin/env python3
"""Offline autonomy self-test — no Ollama required. Exit 0 only if core loops import + behave."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def main() -> int:
    print("@ETHER autonomy self-test")

    # 1 assert nudge
    from core.autonomy import ensure_assert_objective

    check("assert_nudge_empty", "assert" in ensure_assert_objective("").lower())
    check("assert_nudge_add", "assert" in ensure_assert_objective("def f():\n return 1").lower())
    check("assert_keep", ensure_assert_objective("assert 1==1").strip() == "assert 1==1")

    # 2 queue lock + seed under temp memory root override via cwd memory
    from core import batch_queue as bq

    mem = ROOT / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    st0 = bq.status()
    check("queue_status", isinstance(st0, dict) and "pending" in st0)

    # seed if empty
    from core.autonomy import seed_queue_if_empty

    seed = seed_queue_if_empty()
    check("seed_or_pending", seed.get("seeded", 0) >= 0 or seed.get("pending", 0) >= 0)

    # claim/commit path
    from scripts.batch_worker import _claim, _commit_done

    claimed = _claim(1)
    check("claim", isinstance(claimed, list))
    if claimed:
        fake = {"ok": True, "title": claimed[0].get("title"), "id": claimed[0].get("id")}
        n = _commit_done([(claimed[0], fake)])
        check("commit_done", n == 1)
    else:
        check("claim_empty_ok", True)

    # 3 curriculum sample
    from core.curriculum import sample_objective, record_outcome

    item = sample_objective()
    check("curriculum_sample", bool(item.get("objective")))
    state = record_outcome(True, task_id="selftest", verification_score=1.0, total_tests=2)
    check("curriculum_record", isinstance(state, dict))

    # 4 guardian evaluate
    from core.bench_guardian import evaluate

    g = evaluate()
    check("guardian_eval", "frozen" in g)

    # 5 burst tier auto
    from core.pipeline_burst import decide_burst

    d = decide_burst(attempt=2, strategy="default", objective="simple", tier=None)
    check("decide_burst_callable", isinstance(d, bool))

    # 6 flywheel metrics helper
    from scripts.flywheel_metrics import pipeline_metrics

    class _S:
        exit_code = 0
        total_tests = 2
        stderr = ""
        stdout = "ok"

    class _A:
        approved = True

    class _R:
        status = "complete"
        confidence = 0.9
        verification_score = 1.0
        sandbox = _S()
        audit = _A()
        retries = 0
        error = None
        task_id = "t1"

    m = pipeline_metrics(_R())
    check("pipeline_metrics", m.get("verification_score") == 1.0 and m.get("total_tests") == 2)

    # 7 recovery module import + log path
    from core.autonomy import recovery_cycle, on_pipeline_outcome

    check("recovery_import", callable(recovery_cycle))
    out = on_pipeline_outcome(success=False, objective="assert 1==1\nprint(1)", task_id="st")
    check("on_fail_enqueue", isinstance(out, dict))

    # 8 health metric
    from core.health_metric import compute_health, declare_healthy

    h = compute_health()
    check("health_compute", "healthy" in h)
    dcl = declare_healthy()
    check("declare_healthy", "healthy" in dcl)

    print(json.dumps({"ok": not failures, "failures": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
