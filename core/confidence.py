"""Confidence scoring for @ETHER gems."""

from __future__ import annotations

from core.schemas import ClearQuartzResponse


def compute_clear_quartz_confidence(resp: ClearQuartzResponse) -> float:
    """Compute confidence score for Clear Quartz results."""
    test_ratio = resp.tests_passed / max(1, resp.total_tests)
    security_clean = 0.0 if resp.security_flags else 1.0
    speed_ok = 1.0 if resp.execution_time < 30.0 else 0.0
    static_score = max(0.0, min(1.0, resp.static_analysis_score))

    confidence = (
        0.45 * test_ratio
        + 0.30 * security_clean
        + 0.15 * speed_ok
        + 0.10 * static_score
    )

    # Hard safety floors
    if resp.security_flags:
        confidence = min(confidence, 0.25)
    if resp.total_tests == 0:
        confidence = min(confidence, 0.35)

    return round(max(0.0, min(1.0, confidence)), 3)
