"""The calibrated bench must be hard *by measurement*, and must not ship answers.

`memory/quizzes/calibrated_v1.json` exists because three benchmarks in a row
failed to answer whether @ETHER beats the model it runs on. Two leaked their own
assertions into the prompt. The third, `headroom_v1`, fixed every leak, passed
five build-time gates — and then *estimated* the one quantity the experiment's
power depends on. It was built to land a bare model at 0.4-0.7 and measured
0.933: every arm at the ceiling, three to five tasks in disagreement against an
exact-McNemar floor of six, and no possible outcome that could have been
significant. A benchmark that cannot discriminate still produces a number, which
is why it is worse than no benchmark.

This file pins the two properties that make the replacement worth running, and
one new one:

  1. The generator is never shown the answer — objectives are a signature and
     prose, assertions live in `holdout_test`, references live only in
     `scripts/build_calibrated.py`.

  2. The holdouts can fail a wrong answer — mutation scoring at build time,
     with the cheap half of the check repeated here on every run.

  3. NEW: every shipped task carries a *measured* bare-model pass rate, taken
     from three real generations, and no task the bare model solved on all
     three seeds is in the suite. Difficulty is data here, not an adjective in
     a `difficulty` field, and the rejects keep their measurements too — that
     table is the thing this project has never had.

Nothing in this file invokes a model. The measurement is replayed from
`build_calibrated.MEASURED_BARE_RATE`, which is why that table lives in the
source and not in a scratch file.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from core.assert_audit import count_real_asserts
from core.curriculum import check_task_leakage
from core.prompt_guard import assertion_lines, check as prompt_check
from scripts import build_calibrated as bc

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "memory" / "quizzes" / "calibrated_v1.json"

# memory/ is gitignored, so this dataset is a LOCAL artifact absent on a fresh
# clone. Every test here must skip, not fail: pytest is a static gate in the
# flywheel, so one unguarded test drops an entire machine out of the loop.
# That is precisely how the Windows box was lost twice — an unguarded symlink
# test, then this. Module-level so a new test cannot forget the guard.
pytestmark = pytest.mark.skipif(
    not DATASET.exists(),
    reason="memory/quizzes/calibrated_v1.json absent — run scripts/build_calibrated.py to build it",
)

PUBLIC_FIELDS = {
    "id",
    "title",
    "objective",
    "holdout_test",
    "difficulty",
    "bare_pass_rate",
    "bare_passes",
    "bare_seeds",
    "band",
    "power",
}


@pytest.fixture(scope="module")
def document():
    # SKIP, do not fail. memory/ is gitignored, so this dataset is a local
    # artifact that does not exist on a fresh clone. Failing here takes out
    # `pytest`, which is a static gate in the flywheel — so a machine that has
    # simply never run the builder drops out of the loop entirely. That is
    # exactly how the Windows box was lost to an unguarded symlink test.
    if not DATASET.exists():
        pytest.skip(
            "memory/quizzes/calibrated_v1.json absent (gitignored local artifact) — "
            "run `python scripts/build_calibrated.py` to build it"
        )
    return json.loads(DATASET.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tasks(document):
    return document["tasks"]


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_suite_is_large_enough_to_resolve_a_difference(tasks):
    """Size is counted in INFORMATIVE tasks, not in tasks.

    A suite of forty where thirty are at the ceiling has the power of ten —
    which is the arithmetic `headroom_v1` never did. Only tasks the bare model
    passes sometimes can move between arms, so those are the sample; the floor
    tasks ship for a different reason and are counted separately.
    """
    informative = [t for t in tasks if t["power"] == "informative"]
    assert len(informative) >= 12, (
        f"only {len(informative)} tasks carry signal — the suite is a difficulty "
        "distribution, not an experiment"
    )
    assert len(tasks) >= 20


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
    """A name graded elsewhere measures recall of that run, not programming.

    `bc.existing_names()` deliberately extends the headroom check with
    `headroom_v1.json` itself: those forty tasks have been generated against
    this same model dozens of times.
    """
    blocked = bc.existing_names()
    clashes = {t["title"]: blocked[t["title"]] for t in tasks if t["title"] in blocked}
    assert not clashes, f"names already graded elsewhere: {clashes}"


def test_headroom_names_are_actually_blocked():
    """The extension above is load-bearing, so it is checked rather than trusted."""
    blocked = bc.existing_names()
    assert "parse_roman" in blocked and blocked["parse_roman"].endswith("headroom_v1.json")


# ---------------------------------------------------------------------------
# The measurement — the point of this suite
# ---------------------------------------------------------------------------


def test_every_shipped_task_carries_a_measured_bare_rate(tasks):
    for task in tasks:
        assert "bare_pass_rate" in task, f"{task['id']}: no measurement"
        assert task["bare_seeds"] == len(bc.CALIBRATION_SEEDS)
        rate = task["bare_pass_rate"]
        assert 0.0 <= rate <= 1.0


def test_no_task_at_the_ceiling_survived_selection(tasks):
    """A task the bare model always solves cannot show that a scaffold helped.

    This is the check `headroom_v1` had no way to make: it shipped forty tasks
    whose true bare rate was 0.933, and the ablation over them was a foregone
    null.
    """
    for task in tasks:
        # Banded on the integer count, deliberately. `bare_pass_rate` is a
        # rounded decimal and 2/3 rounds UP past a two-thirds threshold, which
        # is exactly how nine informative tasks were once dropped as ceiling.
        assert task["bare_passes"] < task["bare_seeds"], (
            f"{task['id']}: bare model solved every seed"
        )
        assert task["bare_passes"] == round(task["bare_pass_rate"] * task["bare_seeds"])


def test_measured_rates_are_possible_outcomes_of_three_seeds(tasks):
    """0, 1/3, 2/3 or 1 and nothing else. A rate of 0.5 would mean the number
    was typed rather than measured."""
    allowed = {round(k / len(bc.CALIBRATION_SEEDS), 4) for k in range(len(bc.CALIBRATION_SEEDS) + 1)}
    for task in tasks:
        assert round(task["bare_pass_rate"], 4) in allowed, task["id"]


def test_floor_tasks_are_shipped_but_never_counted_as_power(tasks):
    """A 0/3 task is a real task and a fake sample.

    If neither arm ever passes it, the pair is dropped by Wilcoxon and
    concordant under McNemar, so it contributes nothing but sample size — and
    sample size is exactly the thing that flatters a power calculation. It
    ships anyway, because a scaffold that cracks one is the result worth
    having, but it is labelled.
    """
    for task in tasks:
        expected = "none" if task["bare_pass_rate"] <= 0.0 else "informative"
        assert task["power"] == expected, task["id"]
        assert task["band"] == bc.band_of(task["bare_pass_rate"])
    informative = [t for t in tasks if t["power"] == "informative"]
    rates = [t["bare_pass_rate"] for t in informative]
    assert rates, "a suite with no informative task cannot detect anything"
    assert all(0.0 < r < 1.0 for r in rates)


def test_the_measured_distribution_is_reported(document):
    """The distribution is the finding, so it ships next to the tasks.

    Difficulty on this task class came out bimodal — most candidates trivial or
    impossible, the middle scarce. Anyone who reads only the pass rate will
    conclude the suite is too hard; anyone who reads the distribution will
    understand why it is the shape it is.
    """
    distribution = document["distribution"]
    assert distribution["candidates"] == len(bc.SPECS)
    assert distribution["generations"] == len(bc.SPECS) * len(bc.CALIBRATION_SEEDS)
    assert sum(distribution["by_band"].values()) == len(bc.SPECS)
    assert sum(distribution["by_rate"].values()) == len(bc.SPECS)


def test_every_candidate_was_calibrated_and_none_was_guessed():
    ids = {s["id"] for s in bc.SPECS}
    measured = set(bc.MEASURED_BARE_RATE)
    assert ids <= measured, f"never calibrated: {sorted(ids - measured)}"
    assert measured <= ids, f"measurement for an unknown task: {sorted(measured - ids)}"


def test_the_rejects_keep_their_measurements(document):
    """The rejects are data. Throwing them away is how the next suite ends up
    guessing its difficulty again."""
    rejected = document["rejected"]
    shipped = {task["id"] for task in document["tasks"]}
    assert rejected, "a suite where nothing was rejected did not select on anything"
    for row in rejected:
        assert row["id"] not in shipped
        assert row["bare_pass_rate"] is not None, f"{row['id']}: reject with no measurement"
        assert row["reason"]
    assert len(rejected) + len(document["tasks"]) == len(bc.SPECS)


def test_selection_never_takes_a_ceiling_task_and_never_drops_an_informative_one():
    """The rule, checked on a synthetic table rather than on its own output.

    The earlier version of this selector chose bucket counts to hit a target
    mean bare rate, which would have thrown away informative tasks to make an
    average look right. Informative tasks are the experiment; they are never
    surplus.
    """
    specs = [
        {"id": f"t{i:02d}", "title": f"f{i}", "difficulty": "hard"} for i in range(60)
    ]
    measured = {s["id"]: [0.0, 1 / 3, 2 / 3, 1.0][i % 4] for i, s in enumerate(specs)}
    chosen = bc.select_ids(specs, measured, limit=20)
    assert all(measured[i] <= bc.MAX_BARE_RATE for i in chosen)
    informative = {i for i, r in measured.items() if bc.band_of(r) == bc.BAND_INFORMATIVE}
    assert informative <= set(chosen), "an informative task was dropped to meet a size cap"
    assert bc.select_ids(specs, measured, limit=20) == bc.select_ids(specs, measured, limit=20)


def test_selection_fills_the_remaining_room_with_floor_tasks():
    specs = [{"id": f"t{i:02d}", "title": f"f{i}"} for i in range(30)]
    measured = {s["id"]: (1 / 3 if i < 5 else 0.0) for i, s in enumerate(specs)}
    chosen = bc.select_ids(specs, measured, limit=12)
    assert len(chosen) == 12
    assert sum(1 for i in chosen if measured[i] > 0) == 5


def test_power_is_simulated_and_states_what_cannot_be_detected(document):
    """`headroom_v1` shipped no power calculation at all and the run that
    followed could not have found an effect if one existed."""
    power = document["power"]
    assert power["n_tasks"] == len(document["tasks"])
    assert power["n_informative"] + power["n_floor"] == power["n_tasks"]
    assert power["mcnemar_min_discordant_pairs"] == 6
    assert power["power_curve"], "a suite with no power curve repeats the last mistake"
    assert power["primary_test"].startswith("wilcoxon")
    assert 0.0 < power["measured_bare_mean_informative"] < 1.0


def test_the_primary_test_is_calibrated_under_the_null(document):
    """A test that fires on noise would make any result meaningless.

    Simulated with no effect at all, the false positive rate must sit near
    alpha. McNemar's comes out lower because an exact test on few discrete
    pairs is conservative — which is also why it has so much less power.
    """
    null = document["power"]["false_positive_rate_at_zero_effect"]
    assert null["wilcoxon"] <= 0.09, null
    assert null["mcnemar"] <= 0.09, null


def test_the_rate_statistic_beats_collapsing_three_seeds_to_one_bit(document):
    """Why the primary statistic changed.

    McNemar on pass@1 throws away two of three seeds and then keeps only the
    disagreements. On this suite's shape that costs most of the power, which is
    a fact about the design and is worth failing on if it ever stops being
    true.
    """
    curve = {row["per_task_lift"]: row for row in document["power"]["power_curve"]}
    row = curve[0.15]
    assert row["wilcoxon_power"] > row["mcnemar_power"]
    assert row["mean_nonzero_pairs"] >= row["mean_discordant_pairs"]


def test_wilcoxon_and_mcnemar_agree_with_their_definitions():
    """The two statistics are new code, so they are checked against values
    that can be worked out by hand rather than trusted."""
    assert bc.mcnemar_p(0, 0) == 1.0
    assert bc.mcnemar_p(6, 0) == pytest.approx(2 * 0.5 ** 6)
    assert bc.mcnemar_p(5, 0) == pytest.approx(2 * 0.5 ** 5)
    assert bc.mcnemar_p(5, 0) > 0.05 >= bc.mcnemar_p(6, 0)  # the floor of six
    assert bc.mcnemar_p(3, 3) == 1.0
    assert bc.mcnemar_floor() == 6

    assert bc.wilcoxon_p([]) == 1.0
    assert bc.wilcoxon_p([0.0, 0.0]) == 1.0
    assert bc.wilcoxon_p([1.0, -1.0]) == pytest.approx(1.0)
    assert bc.wilcoxon_p([1.0] * 10) < 0.01
    assert bc.wilcoxon_p([1.0] * 10) == bc.wilcoxon_p([-1.0] * 10)  # two-sided
    # Four one-third gains prove nothing: the exact signed-rank p is 0.125.
    # Without a continuity correction the normal approximation returned 0.0455
    # here, which would have made the power simulation optimistic.
    assert bc.wilcoxon_p([1 / 3] * 4) > 0.05


def test_the_plug_in_probability_does_not_assume_the_measurement_is_the_truth():
    """0/3 does not mean never and 3/3 does not mean always.

    Taking the measured rate as the parameter would make floor tasks
    impossible by assumption and hand the power calculation a conclusion.
    """
    assert 0.0 < bc._plug_in_p(0.0) < 0.25
    assert bc._plug_in_p(1.0) < 1.0
    assert bc._plug_in_p(0.0) < bc._plug_in_p(1 / 3) < bc._plug_in_p(2 / 3)


# ---------------------------------------------------------------------------
# The answer must not ship with the question
# ---------------------------------------------------------------------------


def test_no_task_carries_a_reference_field(tasks):
    for task in tasks:
        assert "reference" not in task


def test_no_reference_implementation_appears_anywhere_in_the_dataset():
    """Not as a field, not as a substring, not reformatted.

    Checked line by line rather than whole-blob, because the way this
    regresses is someone serialising the spec dict with an extra key or
    pasting a "worked example" lifted from the reference.
    """
    if not DATASET.exists():
        pytest.skip("dataset absent (gitignored local artifact)")
    blob = DATASET.read_text(encoding="utf-8")
    for spec in bc.SPECS:
        for line in spec["reference"].splitlines():
            body = line.strip()
            if len(body) <= 24:
                continue  # `return out` and friends are not evidence of a leak
            assert body not in blob, f"{spec['title']}: reference line leaked into dataset"


def test_public_task_is_an_allowlist_not_a_filter():
    """A spec field added tomorrow must not publish itself."""
    poisoned = dict(bc.SPECS[0])
    poisoned["solution_notes"] = "the answer"
    poisoned["reference"] = "def leaked(): pass"
    published = bc.public_task(poisoned, rate=0.5)
    assert set(published) == PUBLIC_FIELDS
    assert "the answer" not in json.dumps(published)


def test_dataset_on_disk_matches_the_specs_and_the_measurement(document):
    """The file is the artifact of a passing build, not a hand-edited copy.

    Rebuilding from `SPECS` + `MEASURED_BARE_RATE` has to reproduce it byte for
    byte, which also means the shipped measurement cannot be edited without
    editing the table the tests read.
    """
    assert document == bc.build_document(bc.SPECS, bc.MEASURED_BARE_RATE)


# ---------------------------------------------------------------------------
# Gates 1, 2 and the assertion floor, re-checked on the shipped file
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
    """Tautologies, dead branches and assertions swallowed by an enclosing try
    do not count — `count_real_asserts` is the honest number."""
    for task in tasks:
        lines = assertion_lines(task["holdout_test"])
        assert len(lines) >= bc.MIN_ASSERTS, f"{task['id']}: only {len(lines)} assertions"
        real = count_real_asserts(task["holdout_test"])
        assert real >= bc.MIN_ASSERTS, f"{task['id']}: only {real} observable assertions"


def test_holdouts_probe_cases_the_prose_does_not_enumerate(tasks):
    """A holdout that only repeats the objective's examples grades reading."""
    for task in tasks:
        objective = " ".join(task["objective"].split())
        novel = [
            line
            for line in assertion_lines(task["holdout_test"])
            if " ".join(line.split()) not in objective
        ]
        assert len(novel) >= bc.MIN_ASSERTS, f"{task['id']}: holdout only restates the prompt"


def test_static_gates_pass_on_the_specs_as_written():
    assert bc.static_gates(list(bc.SPECS)) == []


# ---------------------------------------------------------------------------
# The mutation machinery — checked without paying for the sandbox
# ---------------------------------------------------------------------------


def test_every_reference_defines_the_entry_point_it_claims():
    for spec in bc.SPECS:
        tree = ast.parse(spec["reference"])
        assert bc.bh._entry_node(tree, spec["title"]) is not None, spec["title"]


def test_every_task_generates_enough_distinct_mutants():
    for spec in bc.SPECS:
        mutants = bc.bh.generate_mutants(spec["reference"], spec["title"])
        assert len(mutants) >= bc.MIN_MUTANTS, f"{spec['title']}: {len(mutants)} mutants"
        assert len(set(mutants)) == len(mutants), f"{spec['title']}: duplicate mutants"
        baseline = ast.unparse(ast.parse(spec["reference"]))
        assert baseline not in mutants, f"{spec['title']}: a 'mutant' is the reference"
        for mutant in mutants:
            compile(mutant, "<mutant>", "exec")


def test_mutants_include_the_degenerate_answers():
    """Return a constant, return the argument. A holdout that survives those is
    not testing behaviour at all, so they are never sampled away."""
    for spec in bc.SPECS:
        mutants = bc.bh.generate_mutants(spec["reference"], spec["title"])
        assert any("return None" in m for m in mutants), spec["title"]


# ---------------------------------------------------------------------------
# The calibration harness — what it sends, and what it restores
# ---------------------------------------------------------------------------


class _Recorder:
    """Stands in for the router so the prompt can be inspected without a GPU."""

    sent = []

    def __init__(self, *args, **kwargs):
        pass

    def execute(self, envelope):
        from core.schemas import ResponseEnvelope, RoseQuartzResponse

        _Recorder.sent.append(envelope)
        return ResponseEnvelope(
            task_id=envelope.task_id,
            source_gem="rose-quartz",
            payload=RoseQuartzResponse(
                content="```python\ndef f():\n    return 1\n```",
                model_used="fake",
                tokens=3,
                confidence_score=0.8,
            ),
        )


def test_the_bare_arm_sends_the_objective_and_nothing_else(monkeypatch):
    """`bare` means one user message. A system prompt, a plan or a retrieved
    snippet would make the measured difficulty a property of the scaffold, and
    the whole point is that it is a property of the task."""
    import gems.rose_quartz.router as router_module

    _Recorder.sent = []
    monkeypatch.setattr(router_module, "RoseQuartz", _Recorder)
    spec = bc.SPECS[0]
    out = bc.bare_generate(spec["objective"], seed=7)

    assert len(_Recorder.sent) == 1
    messages = _Recorder.sent[0].payload.messages
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].content == spec["objective"]
    assert spec["holdout_test"].splitlines()[0] not in messages[0].content
    assert out["code"] == "def f():\n    return 1"  # fences stripped, prose ignored


def test_calibration_pins_decoding_and_puts_the_environment_back():
    """Thinking off is not decoration: with it on, reasoning tokens ate the
    whole `num_predict` budget and 59% of a 360-sample run returned empty or
    timed out, so that experiment measured infrastructure, not code."""
    before = dict(os.environ)
    with bc.calibration_env(seed=5):
        assert os.environ["ETHER_SEED"] == "5"
        assert os.environ["ETHER_THINKING"] == "0"
        assert float(os.environ["ETHER_TEMPERATURE"]) == bc.CALIBRATION_TEMPERATURE
    after = dict(os.environ)
    assert {k: v for k, v in after.items() if k.startswith("ETHER_")} == {
        k: v for k, v in before.items() if k.startswith("ETHER_")
    }


def test_checkpoints_survive_a_torn_last_line(tmp_path):
    """A crash mid-write must cost one sample, not three hours of GPU."""
    path = tmp_path / "samples.jsonl"
    path.write_text(
        json.dumps({"task_id": "cal01", "seed": 1, "passed": True})
        + "\n"
        + '{"task_id": "cal01", "seed": 2, "pas',
        encoding="utf-8",
    )
    done = bc.load_samples(path)
    assert set(done) == {"cal01|1"}


def test_a_failed_generation_is_never_scored_as_a_pass(tmp_path, monkeypatch):
    """An error is a fail. Counting it as anything else is how an earlier run
    reported infrastructure failure as model quality."""
    monkeypatch.setattr(
        bc, "bare_generate", lambda objective, seed: {"code": "", "error": "boom", "seconds": 0.0}
    )
    spec = bc.SPECS[0]
    rates = bc.calibrate([spec], seeds=(1,), path=tmp_path / "s.jsonl", resume=False, verbose=False)
    assert rates[spec["id"]] == 0.0


def test_build_refuses_to_write_without_a_measurement(monkeypatch, tmp_path):
    """Difficulty is measured here. A build that writes anyway would put the
    project back where headroom_v1 left it."""
    monkeypatch.setattr(bc, "MEASURED_BARE_RATE", {})
    monkeypatch.setattr(bc, "OUT_PATH", tmp_path / "never.json")
    code = bc.main(["--static-only", "--only", bc.SPECS[0]["id"]])
    assert code == 5
    assert not (tmp_path / "never.json").exists()


# ---------------------------------------------------------------------------
# Gates 3 and 4 for real — opt-in, because they cost minutes of sandbox time
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("ETHER_CALIBRATED_GRADE") != "1",
    reason="set ETHER_CALIBRATED_GRADE=1 to grade every reference in the sandbox",
)
def test_every_reference_passes_its_own_holdout():
    """The gate that catches an impossible assertion. The sibling dataset once
    shipped `below_zero([1, 2, -3, 1, -2]) is False` for a balance that ends at
    -1: no correct program could pass it, and it scored every model wrong."""
    from core.holdout import grade_against_holdout

    for spec in bc.SPECS:
        verdict = grade_against_holdout(
            spec["reference"], spec["holdout_test"], timeout=bc.REF_TIMEOUT
        )
        assert verdict["ok"], f"{spec['title']}: {verdict['reason']} {verdict['stderr'][-200:]}"


@pytest.mark.skipif(
    os.getenv("ETHER_CALIBRATED_GRADE") != "1",
    reason="set ETHER_CALIBRATED_GRADE=1 to run full mutation scoring",
)
def test_every_holdout_kills_at_least_ninety_percent_of_its_mutants():
    problems, report = bc.dynamic_gates(list(bc.SPECS), jobs=6, verbose=False)
    assert not problems, problems
    assert all(row["score"] >= bc.MIN_MUTATION_SCORE for row in report)
