"""No bench or quiz task may hand the model its own answer.

`scripts/bench.py` used to prompt with, literally:

    Write only Python: def is_even(n):
        return n % 2 == 0
    assert is_even(4) and not is_even(5)
    print(is_even(4))

and score `status == "complete" and exit_code == 0`. A model that echoed the
prompt back passed, so `Bench pass_rate` read 1.000 while measuring
transcription. That number seeds `core/bench_guardian.py`'s baseline ratchet
and gates `core/health_metric.declare_healthy()`, so the primary health signal
was hollow. The same shape was in `memory/quizzes/holdout_v1.json`
("held out" described where the file lived, not what the model saw).

Two rules these tests pin:

  1. Prompts state a signature and describe behaviour; the assertions live in a
     holdout the generator never sees.
  2. The pass criterion is the HOLDOUT verdict. An exit code cannot be the
     evidence, because a transcription task always exits 0.

Every task set is fetched through the harness's own loader, never by reading
the JSON. The equivalent curriculum test read tiers.json directly and stayed
green while `load_tiers()` spliced five answer-leaking scratch tasks into the
last tier at runtime.
"""

from __future__ import annotations

import json
import sys

import pytest

from core.assert_audit import count_real_asserts
from core.curriculum import check_task_leakage

from scripts import bench, dataset_quiz, hidden_quiz, quiz

# name -> callable returning the tasks that harness actually serves.
HARNESSES = {
    "bench_full": lambda: bench.load_tasks(),
    "bench_fast": lambda: bench.load_tasks(fast=True),
    "quiz_holdout": lambda: quiz.load_tasks(),
    "hidden_humaneval": lambda: hidden_quiz.load_tasks(limit=0),
    "dataset": lambda: dataset_quiz.load_tasks(limit=0),
}

# The pre-fix prompt, kept verbatim as the thing that must never pass again.
LEAKED_BENCH_PROMPT = (
    "Write only Python: def is_even(n):\n"
    "    return n % 2 == 0\n"
    "assert is_even(4) and not is_even(5)\n"
    "print(is_even(4))"
)


def _tasks(name):
    tasks = HARNESSES[name]()
    if not tasks:
        pytest.skip(
            f"{name} dataset absent (Day-3: memory/quizzes + memory/datasets "
            "are untracked) — run scripts/fetch_datasets.py or restore local "
            "copies; skipping rather than auditing vacuously"
        )
    return tasks


@pytest.mark.parametrize("name", sorted(HARNESSES))
def test_no_task_leaks_its_answer(name):
    problems = []
    for task in _tasks(name):
        for p in check_task_leakage(task):
            problems.append(f"{task.get('id')}: {p}")
    assert not problems, f"{name} leaks: {problems}"


@pytest.mark.parametrize("name", sorted(HARNESSES))
def test_no_objective_contains_an_assertion(name):
    """Blunter than the AST check, and catches assertions in prose or fences."""
    for task in _tasks(name):
        assert "assert " not in task["objective"], (
            f"{name}/{task.get('id')} states an assertion in the prompt"
        )


@pytest.mark.parametrize("name", sorted(HARNESSES))
def test_every_task_has_an_observable_holdout(name):
    """A holdout of tautologies (or none at all) grades nothing."""
    for task in _tasks(name):
        n = count_real_asserts(task.get("holdout_test") or "")
        assert n >= 1, f"{name}/{task.get('id')} holdout has no observable assertions"


@pytest.mark.parametrize("name", sorted(HARNESSES))
def test_harness_audit_agrees_with_the_detector(name):
    """The guard the scripts run at startup sees the same tasks these tests do."""
    assert bench.audit_tasks(_tasks(name)) == []


def test_bench_task_identity_is_stable():
    """Historical bench_*.json rows compare by position; keep them meaningful."""
    tasks = bench.load_tasks()
    assert [t["id"] for t in tasks] == [f"b{i:02d}" for i in range(1, 16)]
    assert [t["title"] for t in tasks] == [
        "is_even",
        "add",
        "reverse_string",
        "factorial",
        "is_palindrome",
        "max_of_three",
        "count_vowels",
        "flatten",
        "unique",
        "word_count",
        "sum_list",
        "clamp",
        "title_case",
        "gcd",
        "merge_sorted",
    ]
    assert bench.load_tasks(fast=True) == tasks[: bench.FAST_N]


def test_quiz_ids_are_stable():
    """holdout_ids.json blocks these ids from the curriculum; keep them aligned."""
    ids_path = quiz.ROOT / "memory" / "quizzes" / "holdout_ids.json"
    if not ids_path.exists():
        pytest.skip(
            "memory/quizzes/ untracked (Day-3 dataset policy) — restore local "
            "copies to run this check"
        )
    ids = [t["id"] for t in quiz.load_tasks()]
    blocked = json.loads(
        (quiz.ROOT / "memory" / "quizzes" / "holdout_ids.json").read_text(encoding="utf-8")
    )["ids"]
    assert set(ids) <= set(blocked), "a quiz task is not excluded from the curriculum"


def test_detector_catches_the_prompt_this_bench_used_to_ship():
    """Guards the guard: this test must fail on the pre-fix data."""
    problems = check_task_leakage(
        {
            "id": "old_b01",
            "objective": LEAKED_BENCH_PROMPT,
            "holdout_test": "assert is_even(4) is True\n",
        }
    )
    assert any("implementation" in p for p in problems)
    assert bench.audit_tasks([{"id": "old_b01", "objective": LEAKED_BENCH_PROMPT}])


@pytest.mark.parametrize(
    "module,load",
    [
        (quiz, lambda path: quiz.load_tasks(path=path)),
        (hidden_quiz, lambda path: hidden_quiz.load_tasks(limit=0, path=path)),
        (dataset_quiz, lambda path: dataset_quiz.load_tasks(limit=0, sources=(path,))),
    ],
    ids=["quiz", "hidden", "dataset"],
)
def test_audit_sees_tasks_the_loader_produces(module, load, tmp_path):
    """The audit must inspect the loader's output, not the shipped file.

    scripts/expand_holdout.py appends 30 objectives of exactly this shape to
    holdout_v1.json, so a poisoned dataset is a live possibility rather than a
    hypothetical one.
    """
    poisoned = tmp_path / "poisoned.json"
    poisoned.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "leak1",
                        "objective": LEAKED_BENCH_PROMPT,
                        "prompt": LEAKED_BENCH_PROMPT,
                        "holdout_test": "assert is_even(4) is True\n",
                        "hidden_test": "assert is_even(4) is True\n",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    tasks = load(poisoned)
    assert tasks, "loader dropped the task, so the audit would prove nothing"
    assert bench.audit_tasks(tasks), "loader-produced leak went undetected"


@pytest.mark.parametrize(
    "module",
    [bench, quiz, hidden_quiz, dataset_quiz],
    ids=["bench", "quiz", "hidden", "dataset"],
)
def test_harness_refuses_to_run_leaking_tasks(module, monkeypatch):
    """Enforced at the point of use, not only here. No model call is made."""
    poisoned = [
        {
            "id": "leak1",
            "title": "leak",
            "objective": LEAKED_BENCH_PROMPT,
            "holdout_test": "assert is_even(4) is True\n",
        }
    ]

    def _boom(*args, **kwargs):
        raise AssertionError("harness generated against a leaking task")

    monkeypatch.setattr(module, "load_tasks", lambda *a, **k: poisoned)
    monkeypatch.setattr(module, "Pipeline", _boom)
    monkeypatch.setattr(sys, "argv", [module.__name__])
    assert module.main() == 2


# --- the pass criterion itself -------------------------------------------


class _FakeResult:
    """Just enough of PipelineResult for the grading adapter."""

    def __init__(self, holdout_ok=None, code="", status="complete"):
        self.holdout_ok = holdout_ok
        self.generated_code = code
        self.status = status
        self.stages = []


def test_a_clean_exit_is_not_a_pass():
    """The exact defect: 'complete' + exit 0 while the holdout says otherwise."""
    assert bench.grade_run(_FakeResult(holdout_ok=False), "assert True\n")["ok"] is False


def test_holdout_verdict_is_the_pass_criterion():
    assert bench.grade_run(_FakeResult(holdout_ok=True), "assert 1 == 1\n")["ok"] is True


@pytest.mark.parametrize("holdout", ["", "   ", "\n"])
def test_a_task_without_a_holdout_cannot_pass(holdout):
    """Ungradeable is not the same as correct; fail closed."""
    verdict = bench.grade_run(_FakeResult(holdout_ok=True), holdout)
    assert verdict["ok"] is False
    assert "holdout" in verdict["detail"]


def test_ungraded_result_falls_back_to_real_grading():
    """holdout_ok=None (pipeline never graded) must not default to a pass."""
    task = bench.load_tasks(fast=True)[0]
    wrong = _FakeResult(code="def is_even(n):\n    return True\n")
    right = _FakeResult(code="def is_even(n):\n    return n % 2 == 0\n")
    assert bench.grade_run(wrong, task["holdout_test"])["ok"] is False
    assert bench.grade_run(right, task["holdout_test"])["ok"] is True


def test_bench_holdouts_discriminate():
    """A holdout that every implementation passes measures nothing either."""
    from core.holdout import grade_against_holdout

    task = next(t for t in bench.load_tasks() if t["id"] == "b09")  # unique()
    correct = (
        "def unique(xs):\n"
        "    out = []\n"
        "    for x in xs:\n"
        "        if x not in out:\n"
        "            out.append(x)\n"
        "    return out\n"
    )
    # Plausible but wrong: loses the original ordering.
    wrong = "def unique(xs):\n    return sorted(set(xs))\n"
    assert grade_against_holdout(correct, task["holdout_test"])["ok"] is True
    assert grade_against_holdout(wrong, task["holdout_test"])["ok"] is False
