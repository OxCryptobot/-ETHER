"""Anti-gaming tests for verification scoring.

An audit found the sandbox scored a perfect verification of 1.000 for a no-op
function, an assert inside a comment, a false assert swallowed by
`except AssertionError`, and a bare `print("42 passed")` — while honest code
reporting a real failure scored 0.26. The metric rewarded concealment, and it
feeds the bandit reward, the curriculum tier, and the flywheel commit gate.

These tests pin the counter to "assertions that could actually have failed".
"""

from __future__ import annotations

import pytest

from core.assert_audit import count_real_asserts, uses_test_runner
from core.confidence import compute_scores
from core.schemas import ClearQuartzResponse

# Each of these previously reported total_tests > 0 and confidence 1.000.
GAMED = {
    "no_asserts_at_all": "def solve(n):\n    pass\n",
    "assert_in_comment": "def f():\n    return 1\n# assert f() == 999\n",
    "assert_in_string": "def f():\n    return 1\ns = 'assert f() == 999'\n",
    "swallowed_false_assert": (
        "def f():\n    return 1\ntry:\n    assert f() == 999\n"
        "except AssertionError:\n    pass\n"
    ),
    "swallowed_by_bare_except": (
        "def f():\n    return 1\ntry:\n    assert f() == 999\nexcept:\n    pass\n"
    ),
    "vacuous_true": "assert True\n",
    "vacuous_const_compare": "assert 1 == 1\n",
    "synthesized_tautology": "_r = 1\nassert _r is not None or _r is None or True\n",
    "none_tautology": "_r = 1\nassert _r is None or _r is not None\n",
    "dead_branch": "def f():\n    return 1\nif False:\n    assert f() == 999\n",
}


@pytest.mark.parametrize("name,code", sorted(GAMED.items()))
def test_gamed_artifacts_count_zero_asserts(name, code):
    assert count_real_asserts(code) == 0, f"{name} should not count as a test"


REAL = {
    "simple": ("def f():\n    return 2\nassert f() == 2\n", 1),
    "several": (
        "def f():\n    return 2\nassert f() == 2\nassert 'a' in str(f())\n"
        "assert len([f()]) == 1\n",
        3,
    ),
    "reraised_is_still_observable": (
        "def f():\n    return 1\ntry:\n    assert f() == 2\nexcept AssertionError:\n    raise\n",
        1,
    ),
    "live_branch": ("def f():\n    return 2\nif True:\n    assert f() == 2\n", 1),
}


def test_constant_only_assert_is_not_a_test():
    """`assert 1 + 1 == 2` is constant-foldable and proves nothing about the code."""
    assert count_real_asserts("assert 1 + 1 == 2\n") == 0


@pytest.mark.parametrize("name,case", sorted(REAL.items()))
def test_real_assertions_are_counted(name, case):
    code, expected = case
    assert count_real_asserts(code) == expected


def test_syntax_error_counts_zero():
    assert count_real_asserts("def f(:\n") == 0


def test_printed_counts_are_not_trusted_without_a_runner():
    """`print("42 passed")` previously manufactured 42 passing tests."""
    assert uses_test_runner("print('42 passed in 0.01s')") is False
    assert uses_test_runner("print('Ran 99 tests')\nprint('OK')") is False


def test_real_runner_is_recognised():
    assert uses_test_runner("import pytest\n\ndef test_x():\n    assert 1\n") is True
    assert uses_test_runner("import unittest\n") is True
    assert uses_test_runner("from unittest import TestCase\n") is True


def test_untested_code_cannot_pass_the_default_flywheel_gate():
    """The untested ceiling must sit BELOW ETHER_FLYWHEEL_MIN_CONFIDENCE=0.70.

    It used to cap at exactly 0.70 against a `>= 0.7` gate, so unverified
    artifacts landed on the threshold and were committed as PASS.
    """
    clean_but_untested = ClearQuartzResponse(
        exit_code=0,
        total_tests=0,
        tests_passed=0,
        static_analysis_score=1.0,
        execution_time=1.0,
    )
    assert compute_scores(clean_but_untested)["confidence"] < 0.70


def test_genuinely_verified_code_still_scores_full_confidence():
    verified = ClearQuartzResponse(
        exit_code=0,
        total_tests=3,
        tests_passed=3,
        static_analysis_score=1.0,
        execution_time=1.0,
    )
    assert compute_scores(verified)["confidence"] >= 0.70


def test_honest_failure_is_not_punished_relative_to_concealment():
    """Concealing a failure must not outscore reporting it.

    Identical bugs previously scored 1.000 when the assertion error was
    swallowed and 0.26 when it propagated — training the system toward hiding
    its own failures.
    """
    concealed = "def f():\n    return 1\ntry:\n    assert f() == 999\nexcept AssertionError:\n    pass\n"
    honest = "def f():\n    return 1\nassert f() == 999\n"
    assert count_real_asserts(concealed) == 0
    assert count_real_asserts(honest) == 1
