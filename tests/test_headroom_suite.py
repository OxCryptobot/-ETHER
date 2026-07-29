"""The headroom bench must discriminate, and must not ship its own answers.

`memory/quizzes/headroom_v1.json` exists because the 15-task regression bench
is chapter-3 exercises. A bare 35B scores about 1.0 on `is_even`, `add` and
`reverse_string`, so the window in which a scaffold could show an effect is
narrower than run-to-run noise: an ablation over that suite returns "no
difference" whether or not the scaffold works, and a null result that was
guaranteed before the experiment ran is not evidence of anything.

Two properties make the replacement worth measuring, and both are load-bearing
enough to pin here rather than trust:

  1. The generator is never shown the answer. Every objective is a signature
     and prose; the assertions live in `holdout_test`, and the reference
     implementations live in `scripts/build_headroom.py` and are used only for
     mutation scoring. If a reference ever reached the dataset it would be one
     BM25 hit from the prompt — which is exactly how `scripts/bench.py` leaked
     twelve of fifteen assertions into the context it was grading.

  2. The holdouts can actually fail a wrong answer. `build_headroom.py`
     enforces that at build time by mutation scoring against the sandbox
     (>= 0.90 killed per task); these tests re-check the cheap half — the
     static gates and the mutant generator — on every run, and the expensive
     half only when ETHER_HEADROOM_GRADE=1, because grading ~900 programs
     takes minutes and `pytest -q` runs on every flywheel cycle.

Nothing here invokes a model.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from core.assert_audit import count_real_asserts
from core.curriculum import check_task_leakage
from core.prompt_guard import assertion_lines, check as prompt_check
from scripts import build_headroom as bh

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "memory" / "quizzes" / "headroom_v1.json"

# memory/ is gitignored, so this dataset is a LOCAL artifact absent on a fresh
# clone. Every test here must skip, not fail: pytest is a static gate in the
# flywheel, so one unguarded test drops an entire machine out of the loop.
# That is precisely how the Windows box was lost twice — an unguarded symlink
# test, then this. Module-level so a new test cannot forget the guard.
pytestmark = pytest.mark.skipif(
    not DATASET.exists(),
    reason="memory/quizzes/headroom_v1.json absent — run scripts/build_headroom.py to build it",
)

PUBLIC_FIELDS = {"id", "title", "objective", "holdout_test", "difficulty"}


@pytest.fixture(scope="module")
def document():
    # SKIP, do not fail. memory/ is gitignored, so this dataset is a local
    # artifact that does not exist on a fresh clone. Failing here takes out
    # `pytest`, which is a static gate in the flywheel — so a machine that has
    # simply never run the builder drops out of the loop entirely. That is
    # exactly how the Windows box was lost to an unguarded symlink test.
    if not DATASET.exists():
        pytest.skip(
            "memory/quizzes/headroom_v1.json absent (gitignored local artifact) — "
            "run `python scripts/build_headroom.py` to build it"
        )
    return json.loads(DATASET.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tasks(document):
    return document["tasks"]


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_suite_is_large_enough_to_resolve_a_difference(tasks):
    """Fifteen tasks near the ceiling cannot separate two arms; forty can.

    With ~40 items and a bare model somewhere around 0.5, the standard error
    of a pass rate is roughly 0.08, so a real effect of ~0.15 is visible. On
    the old bench every task was already passing, and the whole measurable
    range was +/- one task.
    """
    assert len(tasks) >= 40


def test_every_task_has_exactly_the_public_fields(tasks):
    for task in tasks:
        assert set(task) == PUBLIC_FIELDS, f"{task.get('id')}: unexpected fields {set(task)}"


def test_difficulty_is_declared_and_both_bands_are_present(tasks):
    bands = {task["difficulty"] for task in tasks}
    assert bands <= {"medium", "hard"}
    assert bands == {"medium", "hard"}, "a suite of one difficulty cannot show a gradient"


def test_ids_and_entry_points_are_unique(tasks):
    ids = [task["id"] for task in tasks]
    titles = [task["title"] for task in tasks]
    assert len(set(ids)) == len(ids)
    assert len(set(titles)) == len(titles)


def test_no_entry_point_collides_with_a_suite_already_graded(tasks):
    """A task the model has been scored on elsewhere is a leak, not a task."""
    blocked = bh.existing_names()
    clashes = {t["title"]: blocked[t["title"]] for t in tasks if t["title"] in blocked}
    assert not clashes, f"names already graded elsewhere: {clashes}"


# ---------------------------------------------------------------------------
# The answer must not ship with the question
# ---------------------------------------------------------------------------


def test_no_task_carries_a_reference_field(tasks):
    for task in tasks:
        assert "reference" not in task


def test_no_reference_implementation_appears_anywhere_in_the_dataset():
    """The strong form: not as a field, not as a substring, not reformatted.

    Checked line by line rather than whole-blob, because the way this
    regresses is someone serialising the spec dict with an extra key or
    embedding a "worked example" lifted from the reference.
    """
    if not DATASET.exists():
        pytest.skip("dataset absent (gitignored local artifact)")
    blob = DATASET.read_text(encoding="utf-8")
    for spec in bh.SPECS:
        for line in spec["reference"].splitlines():
            body = line.strip()
            if len(body) <= 24:
                continue  # `return out` and friends are not evidence of a leak
            assert body not in blob, f"{spec['title']}: reference line leaked into dataset"


def test_public_task_is_an_allowlist_not_a_filter():
    """A spec field added tomorrow must not publish itself.

    `{k: v for k, v in spec.items() if k != 'reference'}` would pass every
    other test in this file and silently ship the next secret someone adds.
    """
    poisoned = dict(bh.SPECS[0])
    poisoned["solution_notes"] = "the answer"
    poisoned["reference"] = "def leaked(): pass"
    published = bh.public_task(poisoned)
    assert set(published) == PUBLIC_FIELDS
    assert "the answer" not in json.dumps(published)


def test_dataset_on_disk_matches_the_specs_that_were_verified(document):
    """The file is the artifact of a passing build, not a hand-edited copy."""
    assert document == bh.build_document(bh.SPECS)


# ---------------------------------------------------------------------------
# Gates 1, 2 and the assertion floor (re-checked on the shipped file)
# ---------------------------------------------------------------------------


def test_no_task_leaks_its_own_answer_into_the_objective(tasks):
    for task in tasks:
        problems = check_task_leakage(task)
        assert not problems, f"{task['id']}: {problems}"


def test_no_holdout_assertion_reaches_the_prompt(tasks):
    for task in tasks:
        verdict = prompt_check(task["objective"], task["holdout_test"])
        assert verdict["clean"], f"{task['id']}: {verdict['detail']}"


def test_objectives_state_a_signature_and_nothing_executable(tasks):
    """Prose plus a signature. If the objective parses as a module with a
    function body in it, the task is transcription."""
    for task in tasks:
        assert task["title"] in task["objective"]
        assert "assert " not in task["objective"]
        try:
            tree = ast.parse(task["objective"])
        except SyntaxError:
            continue  # prose does not parse, which is the normal case
        assert not [
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ], f"{task['id']}: objective contains a definition"


def test_every_holdout_carries_at_least_six_observable_assertions(tasks):
    """Three assertions that restate the prompt cannot fail a wrong answer.

    `count_real_asserts` is the honest count: tautologies, dead branches and
    assertions swallowed by an enclosing try do not count.
    """
    for task in tasks:
        lines = assertion_lines(task["holdout_test"])
        assert len(lines) >= bh.MIN_ASSERTS, f"{task['id']}: only {len(lines)} assertions"
        real = count_real_asserts(task["holdout_test"])
        assert real >= bh.MIN_ASSERTS, f"{task['id']}: only {real} observable assertions"


def test_holdouts_probe_cases_the_prose_does_not_enumerate(tasks):
    """A holdout that only repeats the objective's examples grades nothing."""
    for task in tasks:
        objective = " ".join(task["objective"].split())
        novel = [
            line
            for line in assertion_lines(task["holdout_test"])
            if " ".join(line.split()) not in objective
        ]
        assert len(novel) >= bh.MIN_ASSERTS, f"{task['id']}: holdout only restates the prompt"


# ---------------------------------------------------------------------------
# Gate 4's machinery — checked without paying for the sandbox
# ---------------------------------------------------------------------------


def test_every_reference_defines_the_entry_point_it_claims():
    for spec in bh.SPECS:
        tree = ast.parse(spec["reference"])
        assert bh._entry_node(tree, spec["title"]) is not None, spec["title"]


def test_every_task_generates_enough_distinct_mutants():
    """Fifteen is the floor because 0.90 has to be a meaningful threshold.

    With five mutants a single survivor is 0.80 and a suite could be tuned by
    deleting mutants rather than strengthening assertions.
    """
    for spec in bh.SPECS:
        mutants = bh.generate_mutants(spec["reference"], spec["title"])
        assert len(mutants) >= bh.MIN_MUTANTS, f"{spec['title']}: {len(mutants)} mutants"
        assert len(set(mutants)) == len(mutants), f"{spec['title']}: duplicate mutants"
        baseline = ast.unparse(ast.parse(spec["reference"]))
        assert baseline not in mutants, f"{spec['title']}: a 'mutant' is the reference"
        for mutant in mutants:
            compile(mutant, "<mutant>", "exec")


def test_mutants_include_the_degenerate_answers():
    """Return a constant, return the argument. If a holdout survives those it
    is not testing behaviour at all, so they are never sampled away."""
    for spec in bh.SPECS:
        mutants = bh.generate_mutants(spec["reference"], spec["title"])
        assert any("return None" in m for m in mutants), spec["title"]


def test_mutation_engine_rewrites_the_operators_it_claims_to():
    source = "def f(a, b):\n    if a > 0 and b < 10:\n        return a + b\n    return not a\n"
    mutants = bh.generate_mutants(source, "f")
    joined = "\n@@\n".join(mutants)
    assert "a - b" in joined  # +/- swap
    assert ">= 0" in joined  # comparison boundary
    assert " or " in joined  # and/or
    assert "b < 11" in joined or "b < 9" in joined  # off-by-one on a literal
    assert "return a\n" in joined + "\n"  # dropped `not`
    assert "return 0" in joined  # constant return
    assert "return a" in joined  # argument returned unchanged


def test_static_gates_pass_on_the_specs_as_written():
    """The same gate `build_headroom.py` refuses to write without."""
    assert bh.static_gates(list(bh.SPECS)) == []


# ---------------------------------------------------------------------------
# Gates 3 and 4 for real — opt-in, because they cost minutes of sandbox time
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("ETHER_HEADROOM_GRADE") != "1",
    reason="set ETHER_HEADROOM_GRADE=1 to grade every reference in the sandbox",
)
def test_every_reference_passes_its_own_holdout():
    """The gate that catches an impossible assertion.

    The sibling dataset shipped `below_zero([1, 2, -3, 1, -2]) is False` for a
    balance that ends at -1. No correct implementation could pass it, and the
    task silently scored every model as wrong.
    """
    from core.holdout import grade_against_holdout

    for spec in bh.SPECS:
        verdict = grade_against_holdout(
            spec["reference"], spec["holdout_test"], timeout=bh.REF_TIMEOUT
        )
        assert verdict["ok"], f"{spec['title']}: {verdict['reason']} {verdict['stderr'][-200:]}"


@pytest.mark.skipif(
    os.getenv("ETHER_HEADROOM_GRADE") != "1",
    reason="set ETHER_HEADROOM_GRADE=1 to run full mutation scoring",
)
def test_every_holdout_kills_at_least_ninety_percent_of_its_mutants():
    problems, report = bh.dynamic_gates(list(bh.SPECS), jobs=6, verbose=False)
    assert not problems, problems
    assert all(row["score"] >= bh.MIN_MUTATION_SCORE for row in report)
