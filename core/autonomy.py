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
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
LOG_DIR = ROOT / "memory" / "daemon"
AUTONOMY_LOG = LOG_DIR / "autonomy.jsonl"
RECOVERY_STATE = LOG_DIR / "recovery_state.json"

# Recovery is two 30-minute LLM budgets on a shared GPU. It must be bounded.
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_S = 1800
DEFAULT_MAX_BACKOFF_S = 21600  # 6h
# Total wall-clock budget for one recovery. Kept BELOW the daemon's
# ETHER_RECOVERY_COOLDOWN_S (1800s) because the daemon stamps its cooldown
# BEFORE the run: a recovery that outlives the cooldown makes the next one
# immediately eligible, i.e. a ~100% duty cycle on the GPU.
DEFAULT_BUDGET_S = 1500
DEFAULT_STEP_TIMEOUT_S = 600


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
    """Nudge objectives toward verifiable form without rewriting task intent.

    The empty-objective fallback used to hand back a canned task containing
    both the implementation (`return n % 2 == 0`) and the exact assertions it
    would be graded on — precisely what `core.curriculum.check_task_leakage`
    forbids, since the "work" is transcription. It is now signature-only.
    """
    o = (objective or "").strip()
    if not o:
        return (
            "Write only executable Python, no markdown fences.\n\n"
            "Implement:\n\n"
            "def is_even(n: int) -> bool\n\n"
            "Return True when n is an even integer and False otherwise. "
            "Zero counts as even.\n\n"
            "# Required: include at least two assert statements that prove correctness.\n"
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
        title = f"repair:{fail_kind}:{task_id or 'x'}"[:80]
        if any(str(p.get("title") or "").startswith(f"repair:{fail_kind}:") for p in pending[-20:]):
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
    try:
        from core.bench_guardian import evaluate

        d = evaluate()
        _log("guardian_reeval", frozen=d.get("frozen"), reason=d.get("reason"), pass_rate=d.get("pass_rate"))
        return d
    except Exception as e:
        return {"error": str(e)[:160]}


def maybe_reset_baseline_on_recovery() -> Dict[str, Any]:
    """Ratchet the regression baseline UP after a recovery. Never down.

    This used to rewrite baseline.json to the CURRENT pass_rate whenever the
    drop was inside the tolerance, which ratcheted the regression guardian down
    to nothing: 0.95 -> 0.86 -> 0.77 -> 0.68 ... -> 0.41 never froze, because
    every individual step was "within tolerance" of a baseline that had just
    been moved to meet it. Lowering the baseline is now an explicit operator
    action: `core.bench_guardian.set_baseline(rate, allow_lower=True)`.
    """
    if os.getenv("ETHER_GUARDIAN_AUTO_BASELINE", "1") != "1":
        return {"skipped": True}
    try:
        from core.bench_guardian import ensure_baseline, load_baseline, load_latest

        latest = load_latest()
        if not latest:
            return {"skipped": True, "reason": "no_bench"}
        raw = latest.get("pass_rate")
        try:
            rate = float(raw) if raw is not None and not isinstance(raw, bool) else None
        except (TypeError, ValueError):
            rate = None
        if rate is None or not (0.0 <= rate <= 1.0):
            return {"skipped": True, "reason": "bench_pass_rate_invalid", "pass_rate": raw}
        min_rate = float(os.getenv("ETHER_BENCH_MIN_PASS", "0.40"))
        if rate < min_rate:
            return {"skipped": True, "reason": "still_below_min", "pass_rate": rate}

        previous = float((load_baseline() or {}).get("pass_rate") or 0.0)
        new_base = ensure_baseline(latest)
        new_rate = float(new_base.get("pass_rate") or 0.0)
        raised = new_rate > previous
        decision = reevaluate_guardian()
        _log("baseline_recovery", baseline=new_base, raised=raised, guardian=decision)
        return {
            "ok": True,
            "raised": raised,
            "previous": previous,
            "baseline": new_base,
            "guardian": decision,
        }
    except Exception as e:
        return {"error": str(e)[:200]}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def ollama_endpoint() -> Tuple[str, int]:
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    try:
        parsed = urlparse(base if "//" in base else f"http://{base}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 11434
    except Exception:
        host, port = "127.0.0.1", 11434
    return host, int(port)


def ollama_reachable(timeout: float = 1.0) -> bool:
    """Is the local model server accepting connections?

    "Ollama down" is the most likely cause of an unhealthy system, and it is
    also the one case where recovery cannot possibly succeed — bench and quiz
    both need the model. Probing first costs a TCP connect instead of two
    30-minute timeouts.
    """
    host, port = ollama_endpoint()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _load_recovery_state() -> Dict[str, Any]:
    if not RECOVERY_STATE.exists():
        return {"attempts": 0, "last_finish_ts": 0.0, "last_start_ts": 0.0}
    try:
        data = json.loads(RECOVERY_STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"attempts": 0, "last_finish_ts": 0.0}
    except Exception:
        return {"attempts": 0, "last_finish_ts": 0.0}


def _save_recovery_state(state: Dict[str, Any]) -> Dict[str, Any]:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        RECOVERY_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass
    return state


def reset_recovery_backoff() -> Dict[str, Any]:
    """Operator escape hatch after ETHER_RECOVERY_MAX_ATTEMPTS."""
    return _save_recovery_state({"attempts": 0, "last_finish_ts": 0.0, "last_start_ts": 0.0})


def recovery_backoff_s(attempts: int) -> int:
    base = _env_int("ETHER_RECOVERY_BACKOFF_S", DEFAULT_BACKOFF_S)
    cap = _env_int("ETHER_RECOVERY_MAX_BACKOFF_S", DEFAULT_MAX_BACKOFF_S)
    if attempts <= 0:
        return 0
    return int(min(cap, base * (2 ** (attempts - 1))))


def recovery_ready() -> Dict[str, Any]:
    """Bounded backoff gate, measured from the END of the last recovery.

    The daemon stamps its own cooldown BEFORE calling recovery, so a recovery
    slower than the cooldown re-arms itself instantly. This gate is stamped on
    finish, which is what makes the duty cycle bounded regardless of caller.
    """
    state = _load_recovery_state()
    attempts = int(state.get("attempts") or 0)
    last_finish = float(state.get("last_finish_ts") or 0.0)
    now = time.time()
    since = now - last_finish if last_finish else None
    max_attempts = _env_int("ETHER_RECOVERY_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)
    cap = _env_int("ETHER_RECOVERY_MAX_BACKOFF_S", DEFAULT_MAX_BACKOFF_S)

    if attempts >= max_attempts:
        # Exhausted: hold off for the full cap, then allow one more probe
        # rather than staying wedged forever without an operator.
        if since is not None and since < cap:
            return {
                "ready": False,
                "reason": "max_attempts_exhausted",
                "attempts": attempts,
                "retry_in_s": int(cap - since),
            }
        return {"ready": True, "reason": "cap_elapsed_after_exhaustion", "attempts": attempts}

    wait = recovery_backoff_s(attempts)
    if since is not None and since < wait:
        return {
            "ready": False,
            "reason": "backoff",
            "attempts": attempts,
            "retry_in_s": int(wait - since),
        }
    return {"ready": True, "reason": "ok", "attempts": attempts}


def recovery_cycle(force: bool = False) -> Dict[str, Any]:
    """Full self-recovery when health gate fails — bounded, precondition-gated.

    Bounds: exponential backoff from the previous FINISH, a cap on consecutive
    attempts, and a wall-clock budget that keeps one cycle under the caller's
    cooldown. Precondition: the model server must answer, otherwise the two
    LLM steps are guaranteed to burn their timeouts for nothing.
    """
    started_at = time.time()
    report: Dict[str, Any] = {
        "started": datetime.now(timezone.utc).isoformat(),
        "steps": {},
    }

    gate = recovery_ready()
    report["gate"] = gate
    if not gate.get("ready") and not force:
        _log("recovery_skipped", **gate)
        report["skipped"] = True
        report["reason"] = gate.get("reason")
        return report

    state = _load_recovery_state()
    attempts = int(state.get("attempts") or 0)
    if gate.get("reason") == "cap_elapsed_after_exhaustion":
        attempts = 0
    attempts += 1
    state.update({"attempts": attempts, "last_start_ts": started_at})
    _save_recovery_state(state)

    if not ollama_reachable():
        host, port = ollama_endpoint()
        reason = f"ollama_unreachable:{host}:{port}"
        _log("recovery_precondition_failed", reason=reason, attempts=attempts)
        state.update({"last_finish_ts": time.time(), "last_reason": reason})
        _save_recovery_state(state)
        report.update(
            {
                "skipped": True,
                "reason": reason,
                "attempts": attempts,
                "retry_in_s": recovery_backoff_s(attempts),
                "healthy": {"healthy": False, "reasons": [reason]},
                "finished": datetime.now(timezone.utc).isoformat(),
            }
        )
        return report

    budget_s = _env_int("ETHER_RECOVERY_BUDGET_S", DEFAULT_BUDGET_S)
    step_timeout = _env_int("ETHER_RECOVERY_STEP_TIMEOUT_S", DEFAULT_STEP_TIMEOUT_S)

    def _remaining() -> int:
        return int(budget_s - (time.time() - started_at))

    def _step(name: str, args: List[str], timeout: int) -> Dict[str, Any]:
        left = _remaining()
        if left <= 5:
            return {"ok": False, "skipped": True, "reason": "recovery_budget_exhausted"}
        return _run(args, timeout=min(timeout, left))

    _log("recovery_start", attempts=attempts, budget_s=budget_s)

    report["steps"]["seed"] = seed_queue_if_empty()
    report["steps"]["holdout"] = _step(
        "holdout", [PY, str(ROOT / "scripts" / "expand_holdout.py")], 60
    )
    report["steps"]["bench"] = _step(
        "bench", [PY, str(ROOT / "scripts" / "bench.py"), "--fast"], step_timeout
    )
    report["steps"]["quiz"] = _step(
        "quiz", [PY, str(ROOT / "scripts" / "quiz.py"), "--limit", "8"], step_timeout
    )
    report["steps"]["scoreboard"] = _step(
        "scoreboard",
        [PY, "-c", "from core.scoreboard import write_scoreboard; print(write_scoreboard())"],
        60,
    )
    report["steps"]["baseline"] = maybe_reset_baseline_on_recovery()
    report["steps"]["guardian"] = reevaluate_guardian()

    try:
        from core.health_metric import declare_healthy

        report["healthy"] = declare_healthy()
    except Exception as e:
        report["healthy"] = {"healthy": False, "reasons": [str(e)]}

    healed = bool((report.get("healthy") or {}).get("healthy"))
    state.update(
        {
            "attempts": 0 if healed else attempts,
            "last_finish_ts": time.time(),
            "last_reason": "healthy" if healed else "still_unhealthy",
        }
    )
    _save_recovery_state(state)

    report["attempts"] = 0 if healed else attempts
    report["retry_in_s"] = 0 if healed else recovery_backoff_s(attempts)
    report["elapsed_s"] = round(time.time() - started_at, 2)
    report["finished"] = datetime.now(timezone.utc).isoformat()
    _log("recovery_done", healthy=report.get("healthy"), attempts=attempts)
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
    out: Dict[str, Any] = {}
    if not success and objective:
        out["enqueued"] = enqueue_failure(
            objective=objective,
            fail_kind=fail_kind or "runtime",
            task_id=task_id,
            priority=25,
        )
    out["seed"] = seed_queue_if_empty()
    return out
