"""scripts/expand_holdout.py must not re-poison the held-out quiz.

The script appended 30 tasks whose prompts read, literally:

    Write only Python: def product(xs):
        r=1
        for x in xs: r*=x
        return r
    assert product([2,3,4])==24

— the finished implementation plus the assertion it would be graded on. Running
it undid the v2 cleanup of memory/quizzes/holdout_v1.json in one command, after
which scripts/quiz.py refuses to run at all (exit 2).

These tests pin the repaired contract for h21-h50:

  * prompts describe behaviour, the assertions live in `holdout_test`;
  * every holdout can actually fail (real, observable assertions);
  * every task is SOLVABLE — a correct implementation passes it — and
    DISCRIMINATING — a plausible-but-wrong one does not. The sibling dataset
    shipped `he04`, whose holdout asserted a balance was never negative when it
    ends at -1: no correct answer could ever pass, and nothing noticed;
  * the script writes NOTHING when any of that fails.
"""

from __future__ import annotations

import json
import os

import pytest

from core.assert_audit import count_real_asserts
from core.curriculum import check_task_leakage

import scripts.expand_holdout as ex

EXPECTED_IDS = [f"h{n}" for n in range(21, 51)]
TASK_KEYS = {"id", "title", "objective", "holdout_test"}


def _run(code: str, holdout: str) -> bool:
    """Execute `code` then `holdout` in one namespace; True if it survives.

    In-process on purpose: this is repo-authored, side-effect-free code, and it
    keeps the 60 solvable/discriminating checks in milliseconds instead of
    ~20s of sandbox startups. The same pairs are graded for real through
    core.holdout.grade_against_holdout by the script itself (and by the opt-in
    test at the bottom of this file).
    """
    ns: dict = {}
    exec(compile(code + "\n\n" + holdout, "<task>", "exec"), ns)
    return True


# --------------------------------------------------------------------------
# shape of the dataset the script would append
# --------------------------------------------------------------------------


def test_ids_are_h21_to_h50_and_unique():
    """holdout_ids.json blocks these ids from the curriculum; keep them exact."""
    ids = [t["id"] for t in ex.EXTRA]
    assert ids == EXPECTED_IDS
    assert len(set(ids)) == len(ids)


def test_tasks_carry_only_the_v2_fields():
    for task in ex.EXTRA:
        assert set(task) == TASK_KEYS, task.get("id")


@pytest.mark.parametrize("task", ex.EXTRA, ids=lambda t: t["id"])
def test_no_task_leaks_its_answer(task):
    assert check_task_leakage(task) == []


@pytest.mark.parametrize("task", ex.EXTRA, ids=lambda t: t["id"])
def test_holdout_has_real_assertions(task):
    n = count_real_asserts(task["holdout_test"])
    assert n >= 1, "a holdout with nothing observable grades every answer as a pass"
    # The prompt states one behaviour; the holdout has to probe the corners it
    # does not enumerate (empty input, single element, duplicates, negatives,
    # identity arguments), so 1 is the floor and 3 is the contract.
    assert n >= 3, f"{task['id']} holdout only has {n} observable assertions"


@pytest.mark.parametrize("task", ex.EXTRA, ids=lambda t: t["id"])
def test_objective_states_a_signature_and_no_code(task):
    objective = task["objective"]
    assert "def " in objective, "the prompt must name the function it wants"
    for line in objective.splitlines():
        assert not line.strip().startswith("assert "), "assertions belong in the holdout"
        # A signature ends at the argument list. `def f(...):` opens a body,
        # and a body is the answer.
        assert not line.strip().startswith("def ") or not line.rstrip().endswith(":")
        # Prose is flush left; a pasted implementation is indented.
        assert line == line.lstrip(), f"indented line in a prompt: {line!r}"


def test_reference_implementations_never_reach_the_dataset():
    """The graders' answers are the test of the test, not part of the prompt."""
    serialized = json.dumps(ex.EXTRA)
    for task_id, reference in ex.REFERENCE.items():
        body = reference.split("\n", 1)[1]
        assert body.strip() not in serialized, f"{task_id} implementation leaked"
    assert set(ex.REFERENCE) == set(EXPECTED_IDS)
    assert set(ex.WRONG) == set(EXPECTED_IDS)


# --------------------------------------------------------------------------
# every task must be answerable, and every holdout must be able to say no
# --------------------------------------------------------------------------


@pytest.mark.parametrize("task", ex.EXTRA, ids=lambda t: t["id"])
def test_task_is_solvable(task):
    """A correct implementation passes — the check that would have caught he04."""
    _run(ex.REFERENCE[task["id"]], task["holdout_test"])


@pytest.mark.parametrize("task", ex.EXTRA, ids=lambda t: t["id"])
def test_holdout_rejects_a_wrong_implementation(task):
    """A plausible-but-wrong implementation fails — otherwise the task grades nothing."""
    with pytest.raises(BaseException):
        _run(ex.WRONG[task["id"]], task["holdout_test"])


# --------------------------------------------------------------------------
# the audit gates
# --------------------------------------------------------------------------


def test_audit_passes_on_the_shipped_tasks():
    assert ex.audit_tasks(ex.EXTRA) == []


def test_audit_catches_a_leaked_implementation():
    poisoned = dict(ex.EXTRA[0])
    poisoned["objective"] = "Write only Python: def product(xs):\n    return 1\n"
    assert any("implementation" in p for p in ex.audit_tasks([poisoned]))


def test_audit_catches_a_missing_holdout():
    naked = dict(ex.EXTRA[0])
    naked["holdout_test"] = ""
    assert ex.audit_tasks([naked])


def test_audit_catches_a_tautological_holdout():
    vacuous = dict(ex.EXTRA[0])
    vacuous["holdout_test"] = "assert True\nassert 1 == 1\n"
    assert any("no observable assertions" in p for p in ex.audit_tasks([vacuous]))


def test_audit_catches_duplicate_ids():
    assert any("duplicate id" in p for p in ex.audit_tasks([ex.EXTRA[0], ex.EXTRA[0]]))


# --------------------------------------------------------------------------
# the writer: fail closed, touch nothing on any problem
# --------------------------------------------------------------------------


@pytest.fixture
def tmp_dataset(monkeypatch, tmp_path):
    """Point the script at throwaway files — never memory/quizzes/."""
    holdout = tmp_path / "holdout_v1.json"
    ids = tmp_path / "holdout_ids.json"
    monkeypatch.setattr(ex, "HOLDOUT", holdout)
    monkeypatch.setattr(ex, "IDS", ids)
    return holdout, ids


def test_appends_the_tasks_and_is_idempotent(tmp_dataset):
    holdout, ids = tmp_dataset
    holdout.write_text(json.dumps({"version": 2, "tasks": []}), encoding="utf-8")

    assert ex.main(["--skip-grading"]) == 0
    written = json.loads(holdout.read_text(encoding="utf-8"))["tasks"]
    assert [t["id"] for t in written] == EXPECTED_IDS
    assert json.loads(ids.read_text(encoding="utf-8"))["ids"] == EXPECTED_IDS

    assert ex.main(["--skip-grading"]) == 0
    again = json.loads(holdout.read_text(encoding="utf-8"))["tasks"]
    assert again == written, "a second run must not duplicate the tasks"


def test_written_tasks_survive_the_quiz_auditor(tmp_dataset):
    """scripts/quiz.py exits 2 on a leaking dataset; the output must clear it."""
    from scripts.bench import audit_tasks as quiz_audit
    from scripts.quiz import load_tasks

    holdout, _ = tmp_dataset
    assert ex.main(["--skip-grading"]) == 0
    assert quiz_audit(load_tasks(path=holdout)) == []


def test_refuses_to_write_a_leaking_task(tmp_dataset, monkeypatch):
    holdout, ids = tmp_dataset
    poisoned = dict(ex.EXTRA[0])
    poisoned["objective"] = (
        "Write only Python: def product(xs):\n    r = 1\n    for x in xs:\n"
        "        r *= x\n    return r\n"
    )
    monkeypatch.setattr(ex, "EXTRA", [poisoned])

    assert ex.main(["--skip-grading"]) == 2
    assert not holdout.exists(), "wrote a poisoned dataset"
    assert not ids.exists()


def test_refuses_to_extend_an_already_poisoned_file(tmp_dataset):
    """The merged set is audited, so a bad file cannot be grown either."""
    holdout, ids = tmp_dataset
    holdout.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "h00",
                        "objective": "Write only Python: def add(a, b):\n    return a + b\n",
                        "holdout_test": "assert add(1, 2) == 3\n",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    before = holdout.read_text(encoding="utf-8")

    assert ex.main(["--skip-grading"]) == 2
    assert holdout.read_text(encoding="utf-8") == before
    assert not ids.exists()


def test_refuses_to_write_an_unsolvable_holdout(tmp_dataset, monkeypatch):
    """Gate 3 is wired to main(), not just available as a helper."""
    import core.holdout

    holdout, ids = tmp_dataset
    monkeypatch.setattr(
        core.holdout,
        "grade_against_holdout",
        lambda code, test, timeout=60: {"ok": False, "reason": "holdout assertions failed"},
    )

    rc = ex.main([])
    assert rc == 3
    assert not holdout.exists()
    assert not ids.exists()


def test_refuses_to_write_a_non_discriminating_holdout(tmp_dataset, monkeypatch):
    import core.holdout

    holdout, ids = tmp_dataset
    monkeypatch.setattr(
        core.holdout, "grade_against_holdout", lambda code, test, timeout=60: {"ok": True}
    )

    assert ex.main([]) == 3
    assert not holdout.exists()
    assert not ids.exists()


def test_verify_only_writes_nothing(tmp_dataset, monkeypatch):
    import core.holdout

    holdout, ids = tmp_dataset
    grades = iter([{"ok": True}, {"ok": False}] * len(ex.EXTRA))
    monkeypatch.setattr(
        core.holdout, "grade_against_holdout", lambda code, test, timeout=60: next(grades)
    )

    assert ex.main(["--verify-only"]) == 0
    assert not holdout.exists()
    assert not ids.exists()


def test_verify_solvable_reports_an_impossible_assertion():
    """The he04 shape: an assertion no correct implementation can satisfy."""
    impossible = dict(ex.EXTRA[0])
    impossible["holdout_test"] = "assert product([2, 3, 4]) == 25\nprint('ok')"
    problems = ex.verify_solvable([impossible])
    assert any("UNSOLVABLE" in p for p in problems)


def test_verify_solvable_reports_a_holdout_that_cannot_fail():
    """A holdout that only restates the prompt's example certifies everyone."""
    weak = dict(ex.EXTRA[11])  # h32 is_sorted
    weak["holdout_test"] = "assert is_sorted([1, 2, 3]) is True\nprint('ok')"
    problems = ex.verify_solvable([weak])
    assert any("NOT DISCRIMINATING" in p for p in problems)


@pytest.mark.skipif(
    os.getenv("ETHER_HOLDOUT_SANDBOX_CHECK") != "1",
    reason="60 sandbox runs (~20s); set ETHER_HOLDOUT_SANDBOX_CHECK=1",
)
def test_all_tasks_verify_through_the_real_sandbox():
    assert ex.verify_solvable(ex.EXTRA) == []
