"""Confidence scoring for @ETHER gems."""

from __future__ import annotations

from core.schemas import ClearQuartzResponse


def compute_clear_quartz_confidence(resp: ClearQuartzResponse) -> float:
    """Compute confidence score for Clear Quartz results.

    Formal unit tests (pytest-style) still weigh heaviest.
    Successful exit=0 runs without formal tests are no longer hard-capped at 0.35
    so verified demo scripts score honestly.
    """
    security_clean = 0.0 if resp.security_flags else 1.0
    speed_ok = 1.0 if resp.execution_time < 30.0 else 0.0
    static_score = max(0.0, min(1.0, resp.static_analysis_score))
    exit_ok = 1.0 if resp.exit_code == 0 else 0.0

    if resp.total_tests > 0:
        test_ratio = resp.tests_passed / max(1, resp.total_tests)
        confidence = (
            0.45 * test_ratio
            + 0.25 * security_clean
            + 0.15 * exit_ok
            + 0.10 * speed_ok
            + 0.05 * static_score
        )
    else:
        # No formal tests: weight successful execution + cleanliness
        confidence = (
            0.40 * exit_ok
            + 0.30 * security_clean
            + 0.15 * speed_ok
            + 0.15 * static_score
        )
        # Soft ceiling: demo scripts max ~0.60 without unit tests
        confidence = min(confidence, 0.60 if resp.exit_code == 0 else 0.25)

    if resp.security_flags:
        confidence = min(confidence, 0.25)
    if resp.exit_code != 0:
        confidence = min(confidence, 0.20)

    return round(max(0.0, min(1.0, confidence)), 3)
