"""Validation + rollback gate for self-modification proposals.

Under training wheels the local agent may persist proposals and lessons.
It may not rewrite core/. Tutor (Grok) lands core patches via git.
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.improvement_proposal import write_allowed


def validate_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    if not proposal.get("gap"):
        errors.append("missing_gap")
    if not proposal.get("hypothesis"):
        errors.append("missing_hypothesis")
    if not proposal.get("metric"):
        errors.append("missing_metric")
    if not proposal.get("why"):
        errors.append("missing_why")
    if proposal.get("apply_core") is True:
        errors.append("apply_core_forbidden_under_wheels")
    if proposal.get("soft_launch") is True:
        errors.append("soft_launch_forbidden")
    for rel in proposal.get("files") or []:
        if not write_allowed(str(rel)) and str(rel).replace("\\", "/").startswith("core/"):
            errors.append(f"forbidden_write:{rel}")
    ok = not errors
    return {
        "ok": ok,
        "errors": errors,
        "status": "accepted_proposal" if ok else "rejected",
        "rollback": False,
        "note": (
            "Proposal accepted for tutor review. Core files stay teacher-gated."
            if ok
            else "Proposal rejected; no files written to core/."
        ),
    }


def decide_deploy(*, tests_ok: bool, proposal_ok: bool, wheels: bool = True) -> Dict[str, Any]:
    if not proposal_ok:
        return {"deploy": False, "rollback": True, "reason": "proposal_invalid"}
    if not tests_ok:
        return {"deploy": False, "rollback": True, "reason": "tests_failed"}
    if wheels:
        return {
            "deploy": False,
            "rollback": False,
            "reason": "wheels_on_tutor_applies_core",
            "persist_proposal": True,
        }
    return {"deploy": True, "rollback": False, "reason": "wheels_off_not_this_poc"}
