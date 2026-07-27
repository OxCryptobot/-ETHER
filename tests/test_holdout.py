"""Tests for held-out grading — the one signal a model cannot self-author."""

from __future__ import annotations

import pytest

from core.holdout import grade_against_holdout

GOOD = "def is_even(n):\n    return n % 2 == 0\n"
BAD = "def is_even(n):\n    return True\n"
HOLDOUT = "assert is_even(4) is True\nassert is_even(5) is False\n"


def test_correct_code_passes_holdout():
    r = grade_against_holdout(GOOD, HOLDOUT)
    assert r["ok"] is True, r["reason"]
    assert r["exit_code"] == 0
    assert r["asserts"] == 2


def test_wrong_code_fails_holdout():
    """The whole point: self-authored tests would have passed this."""
    r = grade_against_holdout(BAD, HOLDOUT)
    assert r["ok"] is False
    assert r["reason"] == "holdout assertions failed"


def test_noop_code_fails_holdout():
    r = grade_against_holdout("def is_even(n):\n    pass\n", HOLDOUT)
    assert r["ok"] is False


def test_tautological_holdout_is_refused():
    """A holdout of vacuous asserts must not certify anything."""
    r = grade_against_holdout(GOOD, "assert True\nassert 1 == 1\n")
    assert r["ok"] is False
    assert "no observable assertions" in r["reason"]


def test_leaked_holdout_is_refused():
    """If the generated code contains the holdout, the grade is meaningless."""
    leaked = GOOD + "\n" + HOLDOUT
    r = grade_against_holdout(leaked, HOLDOUT)
    assert r["ok"] is False
    assert r["leaked"] is True


@pytest.mark.parametrize("code,test", [("", HOLDOUT), (GOOD, ""), ("", "")])
def test_empty_inputs_fail_closed(code, test):
    assert grade_against_holdout(code, test)["ok"] is False


def test_self_authored_asserts_do_not_help_wrong_code():
    """Wrong code carrying its own passing asserts still fails the holdout."""
    self_graded = BAD + "\nassert is_even(2) is True\n"
    r = grade_against_holdout(self_graded, HOLDOUT)
    assert r["ok"] is False
