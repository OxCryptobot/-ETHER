"""The flywheel gate must fail an artifact that fails held-out assertions.

Before this, the gate was `status complete AND sandbox_exit 0 AND audit
approved AND confidence >= min`. Since confidence with exit 0 is provably
>= 0.65, and the artifact supplied its own assertions, the gate effectively
asked only "did it run". A wrong implementation shipping its own passing
asserts sailed through at conf=1.000.
"""

from __future__ import annotations

import pytest

import scripts.flywheel as fw

WRONG = "def is_even(n):\n    return True\nassert is_even(2) is True\n"
RIGHT = "def is_even(n):\n    return n % 2 == 0\n"
HOLDOUT = "assert is_even(4) is True\nassert is_even(5) is False\nprint('ok')"


def _fake_attempt(code: str) -> dict:
    """A pipeline result that passes every self-graded gate."""
    return {
        "ok": True,
        "status": "complete",
        "confidence": 1.0,
        "verification_score": 1.0,
        "total_tests": 1,
        "audit_approved": True,
        "sandbox_exit": 0,
        "sandbox_stderr": "",
        "sandbox_stdout": "",
        "retries_inside_pipeline": 0,
        "error": None,
        "task_id": "t",
        "fail_kind": "",
        "generated_code": code,
        "duration_s": 0.01,
    }


@pytest.fixture
def stub_pipeline(monkeypatch):
    def _install(code):
        monkeypatch.setattr(fw, "run_pipeline_once", lambda _obj: _fake_attempt(code))

    return _install


def test_wrong_code_fails_the_gate_despite_perfect_self_score(stub_pipeline):
    stub_pipeline(WRONG)
    result = fw.agentic_verify("impl is_even", 0.7, 1, holdout_test=HOLDOUT)
    assert result["ok"] is False, "wrong code passed the gate"
    final = result["attempts"][-1]
    assert final["confidence"] == 1.0  # self-graded score is still perfect
    assert final["holdout_ok"] is False
    assert final["gate_pass"] is False


def test_correct_code_passes_the_gate(stub_pipeline):
    stub_pipeline(RIGHT)
    result = fw.agentic_verify("impl is_even", 0.7, 1, holdout_test=HOLDOUT)
    assert result["ok"] is True
    assert result["attempts"][-1]["holdout_ok"] is True


def test_without_a_holdout_the_gate_is_unchanged(stub_pipeline):
    """Repair tasks carry no holdout; they must not be blocked by its absence."""
    stub_pipeline(WRONG)
    result = fw.agentic_verify("impl is_even", 0.7, 1, holdout_test="")
    assert result["ok"] is True
    assert result["attempts"][-1]["holdout_ok"] is None


def test_holdout_grading_failure_fails_closed(stub_pipeline, monkeypatch):
    """If the holdout cannot be graded, the artifact must not pass."""
    stub_pipeline(RIGHT)
    import core.holdout

    def boom(*_a, **_k):
        raise RuntimeError("sandbox exploded")

    monkeypatch.setattr(core.holdout, "grade_against_holdout", boom)
    result = fw.agentic_verify("impl is_even", 0.7, 1, holdout_test=HOLDOUT)
    assert result["ok"] is False
    assert "holdout error" in (result["attempts"][-1]["holdout_reason"] or "")
