"""Confidence scoring for @ETHER — dual execution vs verification signals."""

from __future__ import annotations

from typing import Dict

from core.schemas import ClearQuartzResponse


def compute_scores(resp: ClearQuartzResponse) -> Dict[str, float]:
    """Return execution_score, verification_score, and combined confidence."""
    security_clean = 0.0 if resp.security_flags else 1.0
    speed_ok = 1.0 if resp.execution_time < 30.0 else 0.0
    static_score = max(0.0, min(1.0, resp.static_analysis_score))
    exit_ok = 1.0 if resp.exit_code == 0 else 0.0

    execution_score = (
        0.55 * exit_ok + 0.25 * security_clean + 0.10 * speed_ok + 0.10 * static_score
    )
    if resp.exit_code != 0:
        execution_score = min(execution_score, 0.20)
    if resp.security_flags:
        execution_score = min(execution_score, 0.25)

    if resp.total_tests > 0:
        test_ratio = resp.tests_passed / max(1, resp.total_tests)
        verification_score = 0.70 * test_ratio + 0.20 * security_clean + 0.10 * static_score
    else:
        # No formal tests: verification is weak even if execution succeeded
        verification_score = 0.35 * exit_ok + 0.40 * security_clean + 0.25 * static_score
        verification_score = min(verification_score, 0.50 if resp.exit_code == 0 else 0.20)

    if resp.security_flags:
        verification_score = min(verification_score, 0.25)

    # Combined: prefer verification when tests exist; else lean execution
    if resp.total_tests > 0:
        confidence = 0.40 * execution_score + 0.60 * verification_score
    else:
        confidence = 0.65 * execution_score + 0.35 * verification_score
        # Soft ceiling without tests (honest)
        confidence = min(confidence, 0.70 if resp.exit_code == 0 else 0.25)

    return {
        "execution_score": round(max(0.0, min(1.0, execution_score)), 3),
        "verification_score": round(max(0.0, min(1.0, verification_score)), 3),
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
    }


def compute_clear_quartz_confidence(resp: ClearQuartzResponse) -> float:
    return compute_scores(resp)["confidence"]
