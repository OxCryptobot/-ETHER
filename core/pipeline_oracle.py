"""Pure repo-oracle gate helper (strangler slice).

Extracted logic twin of pipeline_hooks.apply_repo_oracle_gate.
Does not import Pipeline. Opt-in for future wire only.
"""
from __future__ import annotations

from typing import Any, Dict


def apply_repo_oracle_gate(
    generated: str,
    objective: str,
    *,
    execution_score: float,
    verification_score: float,
    confidence: float,
) -> Dict[str, Any]:
    """After sandbox exit=0, optionally fail on project pytest."""
    try:
        from core.repo_oracle_hook import evaluate_after_sandbox

        o = evaluate_after_sandbox(generated, objective)
    except Exception as e:
        o = {
            "ok": False,
            "score": 0.0,
            "error": f"hook crash: {e}"[:200],
            "enabled": True,
        }
    if o is None or not o.get("enabled"):
        return {"active": False}
    o_ok = bool(o.get("ok"))
    o_score = float(o.get("score") or 0.0)
    ver = min(float(verification_score or 1.0), o_score)
    conf = min(
        float(confidence or 1.0),
        0.4 * float(execution_score or 0.0) + 0.6 * o_score,
    )
    detail = (
        f"score={o_score} fixture={o.get('fixture', '')}"
        + (f" err={o.get('error')}" if o.get("error") else "")
    )[:240]
    last_err = ""
    fail_kind = ""
    if not o_ok:
        last_err = (
            o.get("stderr") or o.get("stdout") or o.get("error") or "repo_oracle failed"
        )[:1500]
        fail_kind = "repo_oracle"
    return {
        "active": True,
        "ok": o_ok,
        "score": o_score,
        "verification_score": ver,
        "confidence": conf,
        "last_err": last_err,
        "fail_kind": fail_kind,
        "detail": detail,
        "repo_oracle_ok": o_ok,
    }
