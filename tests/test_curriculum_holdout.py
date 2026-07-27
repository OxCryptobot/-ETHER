"""The curriculum must not hand the model its own answer.

Objectives used to read, literally:

    Write only Python: def is_even(n):
        return n % 2 == 0
    assert is_even(4) and not is_even(5)

The prompt contained the implementation *and* the assertions it was graded on,
so the task was transcription and the "tests" were pasted into the model's own
prompt. Every `conf=1.000` earned that way measured nothing.

These tests pin the repaired shape: prompts describe behaviour, and the
assertions live in a `holdout_test` the generator never sees.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.curriculum import check_task_leakage

ROOT = Path(__file__).resolve().parents[1]
TIERS = ROOT / "memory" / "curriculum" / "tiers.json"


def _all_tasks():
    data = json.loads(TIERS.read_text(encoding="utf-8"))
    for tier in data.get("tiers") or []:
        for task in tier.get("tasks") or []:
            yield tier.get("name"), task


def test_tiers_file_exists():
    assert TIERS.exists(), "curriculum tiers.json is missing"


@pytest.mark.parametrize("tier,task", list(_all_tasks()), ids=lambda x: x if isinstance(x, str) else x.get("id", "?"))
def test_no_curriculum_task_leaks_its_answer(tier, task):
    problems = check_task_leakage(task)
    assert not problems, f"[{tier}/{task.get('id')}] {problems}"


def test_every_task_has_a_usable_holdout():
    from core.assert_audit import count_real_asserts

    for tier, task in _all_tasks():
        holdout = task.get("holdout_test") or ""
        n = count_real_asserts(holdout)
        assert n >= 1, f"[{tier}/{task.get('id')}] holdout has no observable assertions"


def test_detector_catches_a_leaked_implementation():
    leaked = {
        "id": "x",
        "objective": "Write only Python: def is_even(n):\n    return n % 2 == 0\n",
        "holdout_test": "assert is_even(4) is True\n",
    }
    problems = check_task_leakage(leaked)
    assert any("implementation" in p for p in problems)


def test_detector_catches_a_leaked_assertion():
    leaked = {
        "id": "x",
        "objective": "Implement is_even(n).\nassert is_even(4) is True\n",
        "holdout_test": "assert is_even(4) is True\n",
    }
    problems = check_task_leakage(leaked)
    assert any("leaked into objective" in p for p in problems)


def test_detector_requires_a_holdout():
    problems = check_task_leakage({"id": "x", "objective": "Implement is_even(n)."})
    assert any("no holdout_test" in p for p in problems)


def test_signature_only_objective_is_accepted():
    """A prompt may name the function and describe behaviour."""
    clean = {
        "id": "x",
        "objective": "Implement:\n\ndef is_even(n: int) -> bool\n\nReturn True when n is even.",
        "holdout_test": "assert is_even(4) is True\nassert is_even(5) is False\n",
    }
    assert check_task_leakage(clean) == []


def test_sample_objective_carries_holdout_without_leaking_it():
    from core.curriculum import sample_objective

    item = sample_objective()
    assert "holdout_test" in item
    holdout = item.get("holdout_test") or ""
    if holdout:
        for line in holdout.splitlines():
            if line.strip().startswith("assert "):
                assert line.strip() not in (item.get("objective") or ""), (
                    "holdout assertion leaked into the sampled objective"
                )
