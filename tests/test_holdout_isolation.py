"""The holdout must grade the implementation, not the model's own self-tests.

`core/autonomy.py::ensure_assert_objective` instructs the model to write its
own assertions. Those land at module level and execute BEFORE the appended
holdout, so one bad self-assert aborted the program and a correct
implementation was reported as "holdout assertions failed" — a false negative
attributed to the wrong cause, which then drove tier demotions and repair
requeues.
"""

from __future__ import annotations

import pytest

from core.holdout import grade_against_holdout, strip_module_level_asserts

HOLDOUT = "assert is_even(4) is True\nassert is_even(5) is False\nprint('ok')"
CORRECT = "def is_even(n):\n    return n % 2 == 0\n"
WRONG = "def is_even(n):\n    return True\n"


def test_bad_self_assert_does_not_fail_a_correct_implementation():
    code = CORRECT + "assert is_even(3) is True\n"  # model's own assertion is wrong
    assert grade_against_holdout(code, HOLDOUT)["ok"] is True


def test_good_self_assert_still_passes():
    assert grade_against_holdout(CORRECT + "assert is_even(2) is True\n", HOLDOUT)["ok"] is True


def test_clean_correct_implementation_passes():
    assert grade_against_holdout(CORRECT, HOLDOUT)["ok"] is True


@pytest.mark.parametrize(
    "code",
    [WRONG, WRONG + "assert is_even(2) is True\n"],
    ids=["clean", "with_self_assert"],
)
def test_wrong_implementation_still_fails(code):
    """Stripping self-asserts must not make wrong code pass."""
    assert grade_against_holdout(code, HOLDOUT)["ok"] is False


def test_only_module_level_asserts_are_stripped():
    """In-function assertions are the implementation's own preconditions."""
    code = "def f(n):\n    assert n >= 0\n    return n\nassert f(1) == 1\n"
    stripped = strip_module_level_asserts(code)
    assert "assert n >= 0" in stripped
    assert "assert f(1)" not in stripped


def test_stripping_is_a_noop_without_module_asserts():
    assert strip_module_level_asserts(CORRECT) == CORRECT


def test_unparseable_code_is_returned_unchanged():
    broken = "def f(:\n"
    assert strip_module_level_asserts(broken) == broken


def test_in_function_precondition_failure_still_fails_the_holdout():
    """A precondition the holdout trips is a genuine failure of the code."""
    code = "def is_even(n):\n    assert n < 5, 'unsupported'\n    return n % 2 == 0\n"
    assert grade_against_holdout(code, HOLDOUT)["ok"] is False
