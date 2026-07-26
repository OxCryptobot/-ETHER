from core.schemas import ClearQuartzResponse
from core.confidence import compute_clear_quartz_confidence, compute_scores


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
    """Demo runs without formal tests: dual scores, soft-capped at 0.70."""
    r = ClearQuartzResponse(
        exit_code=0,
        total_tests=0,
        tests_passed=0,
        static_analysis_score=1.0,
        execution_time=1.0,
    )
    scores = compute_scores(r)
    score = scores["confidence"]
    assert score <= 0.70
    assert score >= 0.50  # successful clean exit should not look like failure
    assert scores["execution_score"] >= 0.5
    assert scores["verification_score"] <= 0.50  # weak without formal tests


def test_failed_exit_cap():
    r = ClearQuartzResponse(
        exit_code=1,
        total_tests=0,
        tests_passed=0,
        static_analysis_score=1.0,
        execution_time=1.0,
    )
    assert compute_clear_quartz_confidence(r) <= 0.20
