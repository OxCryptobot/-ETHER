from core.schemas import ClearQuartzResponse
from core.confidence import compute_clear_quartz_confidence


def test_perfect():
    r = ClearQuartzResponse(
        exit_code=0,
        total_tests=5,
        tests_passed=5,
        static_analysis_score=1.0,
        execution_time=1.0,
    )
    assert compute_clear_quartz_confidence(r) == 1.0


def test_security_cap():
    r = ClearQuartzResponse(
        exit_code=0,
        total_tests=5,
        tests_passed=5,
        security_flags=["eval"],
        static_analysis_score=1.0,
    )
    assert compute_clear_quartz_confidence(r) <= 0.25


def test_no_tests_soft_cap():
    """Demo runs without formal tests are soft-capped (~0.60), not 0.35."""
    r = ClearQuartzResponse(
        exit_code=0,
        total_tests=0,
        tests_passed=0,
        static_analysis_score=1.0,
        execution_time=1.0,
    )
    score = compute_clear_quartz_confidence(r)
    assert score <= 0.60
    assert score >= 0.50  # successful clean exit should not look like failure


def test_failed_exit_cap():
    r = ClearQuartzResponse(
        exit_code=1,
        total_tests=0,
        tests_passed=0,
        static_analysis_score=1.0,
        execution_time=1.0,
    )
    assert compute_clear_quartz_confidence(r) <= 0.20
