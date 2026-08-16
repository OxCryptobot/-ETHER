"""Mandatory Labradorite on non-infra FAIL + PlanState replan.

Critical fix #7: enqueue at most one recovery per failure_type per hour.
Phase 1D: refresh critique_plan_wire after each critique artifact.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
CRITIQUE_DIR = ROOT / "artifacts" / "critiques"
PENDING = ROOT / "artifacts" / "jobs" / "pending"

INFRA_KINDS = {
    "infra",
    "dependency",
    "timeout_infra",
    "plan",
    "exception_infra",
}
INFRA_SIGS = (
    "cannot connect to the docker daemon",
    "failed to connect to the docker api",
    "cannot connect to ollama",
    "connection refused",
    "max retries exceeded",
    "name or service not known",
    "no such host",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_infra_fail(
    *,
    failure_type: str = "",
    fail_kind: str = "",
    stderr: str = "",
    note: str = "",
) -> bool:
    fk = (failure_type or fail_kind or "").strip().lower()
    if fk in INFRA_KINDS:
        return True
    hay = f"{stderr} {note}".lower()
    return any(s in hay for s in INFRA_SIGS)


def _run_labradorite(code: str = "", objective: str = "") -> Dict[str, Any]:
    try:
        from core.schemas import Envelope, LabradoriteRequest
        from gems.labradorite.profiler import Labradorite

        gem = Labradorite()
        body = code or (
            f"# fail context\n# objective: {objective[:200]}\n"
            "# no code artifact — critique failure envelope only\n"
        )
        env = Envelope(
            task_id=uuid4(),
            target_gem="labradorite",
            payload=LabradoriteRequest(code=body[:8000], language="python"),
        )
        res = gem.execute(env)
        if res.error:
            return {
                "ok": False,
                "error": res.error.message,
                "critique": f"labradorite error: {res.error.message}",
                "suggested_improvements": [],
            }
        payload = res.payload
        return {
            "ok": True,
            "critique": getattr(payload, "critique", "") or "",
            "suggested_improvements": list(
                getattr(payload, "suggested_improvements", []) or []
            ),
            "complexity_score": getattr(payload, "complexity_score", 0.5),
            "confidence_score": getattr(payload, "confidence_score", 0.5),
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "critique": f"critique_unavailable: {type(e).__name__}",
            "suggested_improvements": [],
        }


def _next_hypothesis(failure_type: str, suggestions: List[str]) -> str:
    try:
        from core.plan_state import plan_from_failure

        plan = plan_from_failure(
            objective=suggestions[0] if suggestions else failure_type,
            failure_type=failure_type or "unknown",
        )
        if plan.get("hypothesis"):
            return str(plan["hypothesis"])[:200]
    except Exception:
        pass
    ft = (failure_type or "").lower()
    if ft in ("timeout", "budget_exhaust", "max_steps"):
        return "reduce scope: one file, one assert, tool_runtime scripted only"
    if ft == "no_progress":
        return "re-read failing test; single apply_patch; abort after one more stagnant fail"
    if ft == "tool_runtime_failed_terminal":
        return "do not generate-fallback; diagnose tool parse/AST; requeue scripted hard"
    if suggestions:
        return suggestions[0][:200]
    return "smallest experiment: read tests → one surgical patch → run_tests"


def critique_fail(
    *,
    job_id: str,
    failure_type: str = "",
    fail_kind: str = "",
    note: str = "",
    stderr: str = "",
    code: str = "",
    objective: str = "",
    enqueue: bool = True,
) -> Dict[str, Any]:
    if is_infra_fail(
        failure_type=failure_type, fail_kind=fail_kind, stderr=stderr, note=note
    ):
        return {
            "skipped": True,
            "reason": "infra_fail",
            "job_id": job_id,
            "failure_type": failure_type or fail_kind,
        }

    lab = _run_labradorite(code=code, objective=objective or note)
    ft = failure_type or fail_kind or "unknown"
    hyp = _next_hypothesis(ft, lab.get("suggested_improvements") or [])
    plan_meta: Dict[str, Any] = {}
    try:
        from core.plan_state import plan_from_failure

        plan_meta = plan_from_failure(
            objective=objective or note or job_id,
            failure_type=ft,
        )
        if plan_meta.get("hypothesis"):
            hyp = str(plan_meta["hypothesis"])[:200]
    except Exception:
        pass

    artifact = {
        "id": f"critique_{job_id}_{datetime.now(timezone.utc).strftime('%H%M%S')}",
        "job_id": job_id,
        "created": _now(),
        "failure_type": ft,
        "note": (note or "")[:300],
        "labradorite_ok": bool(lab.get("ok")),
        "critique": lab.get("critique") or "",
        "suggested_improvements": lab.get("suggested_improvements") or [],
        "next_hypothesis": hyp,
        "plan": plan_meta,
        "source": "critique_on_fail",
        "mandatory": True,
    }
    CRITIQUE_DIR.mkdir(parents=True, exist_ok=True)
    path = CRITIQUE_DIR / f"{artifact['id']}.json"
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    artifact["path"] = str(path.relative_to(ROOT)).replace("\\", "/")

    # Phase 1D: keep board PlanState wire fresh after every FAIL critique
    try:
        from core.critique_plan_wire import wire_latest

        wire = wire_latest()
        artifact["plan_wire"] = {
            "n_replanned": wire.get("n_replanned"),
            "latest_hypothesis": wire.get("latest_hypothesis"),
        }
    except Exception:
        pass

    enqueued_id = None
    if enqueue:
        try:
            from core.playbook_limiter import allow_playbook, mark_playbook

            if not allow_playbook(ft, "labradorite"):
                artifact["enqueued"] = None
                artifact["enqueue_skipped"] = "rate_limited"
                return artifact
            enqueued_id = _enqueue_hypothesis_job(job_id, hyp, ft)
            if enqueued_id:
                mark_playbook(ft, "labradorite")
        except Exception:
            enqueued_id = _enqueue_hypothesis_job(job_id, hyp, ft)
        artifact["enqueued"] = enqueued_id
    return artifact


def _enqueue_hypothesis_job(
    failed_job_id: str, hypothesis: str, failure_type: str
) -> Optional[str]:
    try:
        from core.queue_governor import may_enqueue

        if not may_enqueue():
            return None
    except Exception:
        pass
    try:
        PENDING.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        safe = re.sub(r"[^\w\-]+", "_", failed_job_id)[:40]
        jid = f"critique_hyp_{safe}_{stamp}"
        job = {
            "id": jid,
            "class": "recovery",
            "source": "labradorite_mandatory",
            "created": _now(),
            "note": f"playbook:labradorite for {failed_job_id} [{failure_type}] :: {hypothesis[:120]}",
            "continue_on_fail": True,
            "steps": [
                {
                    "argv": [
                        ".venv/Scripts/python.exe",
                        "-m",
                        "pytest",
                        "tests/test_tool_runtime.py",
                        "tests/test_train_gates.py",
                        "tests/test_honest_live_critique_context.py",
                        "-q",
                        "--tb=line",
                    ],
                    "timeout": 180,
                }
            ],
        }
        (PENDING / f"{jid}.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
        return jid
    except Exception:
        return None


def critique_from_last_job(enqueue: bool = True) -> Dict[str, Any]:
    last_path = ROOT / "artifacts" / "host_agent_last_job.json"
    if not last_path.exists():
        return {"skipped": True, "reason": "no_last_job"}
    try:
        last = json.loads(last_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"skipped": True, "reason": f"bad_last_job:{e}"}
    if last.get("ok") is not False:
        return {"skipped": True, "reason": "last_job_ok"}
    return critique_fail(
        job_id=str(last.get("job_id") or "unknown"),
        failure_type=str(last.get("failure_type") or ""),
        note=str(last.get("note") or ""),
        stderr=str(last.get("stderr") or ""),
        enqueue=enqueue,
    )
