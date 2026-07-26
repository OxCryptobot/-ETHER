"""Shared metrics extraction for flywheel agentic attempts."""

from __future__ import annotations

from typing import Any, Dict


def pipeline_metrics(result: Any) -> Dict[str, Any]:
    """Normalize PipelineResult → gate fields including verification."""
    audit_ok = bool(getattr(result, "audit", None) and result.audit.approved)
    confidence = float(getattr(result, "confidence", 0.0) or 0.0)
    sandbox = getattr(result, "sandbox", None)
    sandbox_ok = bool(sandbox and sandbox.exit_code == 0)
    stderr = (sandbox.stderr or "")[-800:] if sandbox else ""
    stdout = (sandbox.stdout or "")[-400:] if sandbox else ""
    verification = float(getattr(result, "verification_score", 0.0) or 0.0)
    total_tests = int(sandbox.total_tests) if sandbox else 0
    if verification == 0.0 and sandbox is not None:
        try:
            from core.confidence import compute_scores

            scores = compute_scores(sandbox)
            verification = float(scores.get("verification_score") or 0.0)
            confidence = float(scores.get("confidence") or confidence)
        except Exception:
            pass
    return {
        "ok": getattr(result, "status", "") == "complete" and sandbox_ok and audit_ok,
        "status": getattr(result, "status", "error"),
        "confidence": confidence,
        "verification_score": verification,
        "total_tests": total_tests,
        "audit_approved": audit_ok,
        "sandbox_exit": sandbox.exit_code if sandbox else None,
        "sandbox_stderr": stderr,
        "sandbox_stdout": stdout,
        "retries_inside_pipeline": int(getattr(result, "retries", 0) or 0),
        "error": getattr(result, "error", None),
        "task_id": str(getattr(result, "task_id", "") or ""),
        "fail_kind": "runtime" if not sandbox_ok else "",
    }
