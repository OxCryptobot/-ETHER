"""Autonomy core — recovery, failure requeue, guardian re-eval.

Design rule: if the human walks away, this module + daemon must still:
  1) detect unhealthy
  2) run recovery metrics (bench/quiz/scoreboard)
  3) re-evaluate guardian
  4) requeue hard failures into batch with asserts
  5) keep flywheel/curriculum moving
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
LOG_DIR = ROOT / "memory" / "daemon"
AUTONOMY_LOG = LOG_DIR / "autonomy.jsonl"


def _log(event: str, **payload: Any) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **payload}
    try:
        with AUTONOMY_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


def _run(args: List[str], timeout: int = 1800) -> Dict[str, Any]:
    try:
        p = subprocess.run(
            args,
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": p.returncode == 0,
            "returncode": p.returncode,
            "stdout": (p.stdout or "")[-2000:],
            "stderr": (p.stderr or "")[-1000:],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def ensure_assert_objective(objective: str) -> str:
    """Nudge objectives toward verifiable form without rewriting task intent."""
    o = (objective or "").strip()
    if not o:
        return (
            "Write only Python with asserts:\n"
            "def is_even(n):\n    return n % 2 == 0\n"
            "assert is_even(4) is True\n"
            "assert is_even(5) is False\n"
            "print('ok')\n"
        )
    low = o.lower()
    if "assert " in low or "assert(" in low:
        return o
    return (
        o.rstrip()
        + "\n\n# Required: include at least two assert statements that prove correctness.\n"
        + "# Return only executable Python, no markdown fences.\n"
    )


def enqueue_failure(
    *,
    objective: str,
    fail_kind: str = "runtime",
    task_id: str = "",
    priority: int = 30,
) -> Optional[Dict[str, Any]]:
    """Push a failed objective back onto the batch queue with assert pressure."""
    if os.getenv("ETHER_AUTO_ENQUEUE", "1") != "1":
        return None
    try:
        from core.batch_queue import enqueue, load_queue

        data = load_queue()
        pending = data.get("pending") or []
        # de-dupe by title prefix
        title = f"repair:{fail_kind}:{task_id or 'x'}"[:80]
        if any(str(p.get("title") or "").startswith(f"repair:{fail_kind}:") for p in pending[-20:]):
            # avoid flooding same kind
            if sum(1 for p in pending if str(p.get("title") or "").startswith("repair:")) >= 8:
                return {"skipped": True, "reason": "too_many_repairs_pending"}

        item = enqueue(
            kind="pipeline",
            title=title,
            objective=ensure_assert_objective(objective),
            priority=priority,
        )
        _log("enqueue_failure", title=title, task_id=task_id, fail_kind=fail_kind)
        return item
    except Exception as e:
        _log("enqueue_failure_error", error=str(e)[:160])
        return None


def seed_queue_if_empty() -> Dict[str, Any]:
    try:
        from core.batch_queue import seed_smoke, status

        st = status()
        if st.get("pending", 0) > 0:
            return {"seeded": 0, "pending": st["pending"]}
        out = seed_smoke(force=False)
        _log("seed_queue", **out)
        return out
    except Exception as e:
        return {"error": str(e)[:160]}


def reevaluate_guardian() -> Dict[str, Any]:
    """Re-run guardian against latest bench; may unfreeze if metrics recovered."""
    try:
        from core.bench_guardian import evaluate

        d = evaluate()
        _log("guardian_reeval", frozen=d.get("frozen"), reason=d.get("reason"), pass_rate=d.get("pass_rate"))
        return d
    except Exception as e:
        return {"error": str(e)[:160]}


def maybe_reset_baseline_on_recovery() -> Dict[str, Any]:
    """If pass_rate recovered above baseline-drop, optionally lift freeze by refreshing baseline.

    Controlled by ETHER_GUARDIAN_AUTO_BASELINE=1 (default on for autonomy mode).
    """
    if os.getenv("ETHER_GUARDIAN_AUTO_BASELINE", "1") != "1":
        return {"skipped": True}
    try:
        from core.bench_guardian import load_latest, GUARD_PATH, BASELINE_PATH, ensure_baseline

        latest = load_latest()
        if not latest:
            return {"skipped": True, "reason": "no_bench"}
        rate = float(latest.get("pass_rate") or 0.0)
        min_rate = float(os.getenv("ETHER_BENCH_MIN_PASS", "0.40"))
        if rate < min_rate:
            return {"skipped": True, "reason": "still_below_min", "pass_rate": rate}

        # If frozen only due to regression vs old baseline, and current rate is stable enough,
        # move baseline forward so autonomy can continue (still requires min_rate).
        base = {}
        if BASELINE_PATH.exists():
            try:
                base = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
            except Exception:
                base = {}
        baseline = float(base.get("pass_rate") or 0.0)
        drop_tol = float(os.getenv("ETHER_BENCH_DROP_TOL", "0.10"))
        if baseline > 0 and (baseline - rate) > drop_tol:
            # still in regression — do not auto-lift
            return {"skipped": True, "reason": "still_regressed", "baseline": baseline, "pass_rate": rate}

        # recovered or never regressed — ensure baseline tracks recent healthy rate
        new_base = ensure_baseline(latest)
        # force rewrite baseline to current when recovered
        if rate >= min_rate:
            new_base = {
                "pass_rate": rate,
                "n": latest.get("n"),
                "set_at": datetime.now(timezone.utc).isoformat(),
                "source": "autonomy_recovery",
            }
            BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
            BASELINE_PATH.write_text(json.dumps(new_base, indent=2), encoding="utf-8")
        decision = reevaluate_guardian()
        _log("baseline_recovery", baseline=new_base, guardian=decision)
        return {"ok": True, "baseline": new_base, "guardian": decision}
    except Exception as e:
        return {"error": str(e)[:200]}


def recovery_cycle() -> Dict[str, Any]:
    """Full self-recovery when health gate fails.

    Steps:
      1. seed batch if empty
      2. fast bench
      3. short quiz
      4. scoreboard
      5. baseline/guardian re-eval
      6. declare_healthy again
    """
    report: Dict[str, Any] = {"started": datetime.now(timezone.utc).isoformat(), "steps": {}}
    _log("recovery_start")

    report["steps"]["seed"] = seed_queue_if_empty()

    report["steps"]["bench"] = _run(
        [PY, str(ROOT / "scripts" / "bench.py"), "--fast"],
        timeout=1800,
    )
    report["steps"]["quiz"] = _run(
        [PY, str(ROOT / "scripts" / "quiz.py"), "--limit", "5"],
        timeout=1800,
    )
    report["steps"]["scoreboard"] = _run(
        [PY, "-c", "from core.scoreboard import write_scoreboard; print(write_scoreboard())"],
        timeout=60,
    )
    report["steps"]["baseline"] = maybe_reset_baseline_on_recovery()
    report["steps"]["guardian"] = reevaluate_guardian()

    try:
        from core.health_metric import declare_healthy

        report["healthy"] = declare_healthy()
    except Exception as e:
        report["healthy"] = {"healthy": False, "reasons": [str(e)]}

    report["finished"] = datetime.now(timezone.utc).isoformat()
    _log("recovery_done", healthy=report.get("healthy"))
    return report


def on_pipeline_outcome(
    *,
    success: bool,
    objective: str,
    task_id: str = "",
    verification_score: float = 0.0,
    total_tests: int = 0,
    fail_kind: str = "runtime",
    stderr: str = "",
) -> Dict[str, Any]:
    """Called after agentic attempts — curriculum already updated elsewhere; we requeue fails."""
    out: Dict[str, Any] = {}
    if not success and objective:
        out["enqueued"] = enqueue_failure(
            objective=objective,
            fail_kind=fail_kind or "runtime",
            task_id=task_id,
            priority=25,
        )
    # keep queue fed
    out["seed"] = seed_queue_if_empty()
    return out
