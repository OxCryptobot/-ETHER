"""Typed failure taxonomy for host + tool runtime + playbooks.

Goal: timeouts and budget exhaust are not opaque rc=1 — they carry a
failure_type that foreman lessons and GEMS can match.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Canonical failure types (string constants for JSON envelopes)
TIMEOUT = "timeout"
BUDGET_EXHAUST = "budget_exhaust"
NO_PROGRESS = "no_progress"
TOOL_RUNTIME_TERMINAL = "tool_runtime_failed_terminal"
STEP_FAIL = "step_fail"
BAD_JOB = "bad_job"
EXCEPTION = "exception"
UNKNOWN = "unknown"


def classify_host_error(exc: BaseException) -> str:
    """Map a raised exception to a failure_type."""
    name = type(exc).__name__
    if name == "TimeoutExpired" or "timeout" in str(exc).lower():
        return TIMEOUT
    return EXCEPTION


def classify_runtime_error(error: str, reason: str = "") -> str:
    """Map ToolRuntime error/reason fields."""
    hay = f"{error} {reason}".lower()
    if "no_progress" in hay:
        return NO_PROGRESS
    if "timeout" in hay:
        return TIMEOUT
    if "max_steps" in hay or "budget" in hay:
        return BUDGET_EXHAUST
    if "tool_runtime_failed_terminal" in hay:
        return TOOL_RUNTIME_TERMINAL
    if error:
        return STEP_FAIL
    return UNKNOWN


def envelope(
    *,
    job_id: str,
    ok: bool,
    rc: int,
    note: Optional[str] = None,
    failure_type: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build last_job / failed envelope with optional typed failure."""
    from datetime import datetime, timezone

    out: Dict[str, Any] = {
        "job_id": job_id,
        "ok": ok,
        "rc": rc,
        "finished": datetime.now(timezone.utc).isoformat(),
        "note": note,
    }
    if not ok and failure_type:
        out["failure_type"] = failure_type
    if extra:
        out.update(extra)
    return out
