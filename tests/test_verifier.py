"""Tests for core/verifier.py — the holdout-free correctness score.

Sandbox-backed cases are grouped and marked so they can be deselected; they
run real code through gems.clear_quartz.sandbox.ClearQuartz, which is the
point of the signal and cannot be faked without testing a different thing.

Nothing here depends on a gitignored artifact, so nothing here can take a
machine out of the flywheel (docs/FINDINGS.md §9). The ruff-dependent tests
skip when ruff is absent rather than fail.
"""

from __future__ import annotations

import ast

import pytest

from core import verifier


HAS_RUFF = verifier._ruff_bin() is not None
needs_ruff = pytest.mark.skipif(not HAS_RUFF, reason="ruff is not installed")


def _sandbox_works() -> bool:
    """Can we execute at all? Docker may be absent/down on this machine."""
    run = verifier._run_probe(
        verifier._build_probe("x = 1\n", "", [], {}), timeout=30
    )
    return bool(run["ok"])


SANDBOX_OK = _sandbox_works()
needs_sandbox = pytest.mark.skipif(
    not SANDBOX_OK, reason="no working sandbox (docker down and no local python?)"
)


GOOD = """
def dedupe(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
"""

MUTATES = """
def dedupe(items):
    items.sort()
    return sorted(set(items))
"""

UNDEFINED = """
def dedupe(items):
    return mystery_helper(items)
"""

CRASHES = """
def dedupe(items):
    return items[99]
"""


# ---------------------------------------------------------------------------
# the parse gate
# ---------------------------------------------------------------------------


def test_syntax_error_is_a_hard_zero():
    out = verifier.score("def broken(:\n  pass", "anything", run_sandbox=False)
    assert out["score"] == 0.0
    assert out["signals"]["parses"] == 0.0
    assert any("SyntaxError" in d for d in out["diagnostics"])


def test_empty_code_scores_zero_and_says_why():
    out = verifier.score("", "anything", run_sandbox=False)
    assert out["score"] == 0.0
    assert any("empty candidate" in d for d in out["diagnostics"])


def test_score_never_raises_on_hostile_input():
    for junk in [None, "", "\x00\x01", "def f(:", "```python\ndef f():\n  pass\n```"]:
        out = verifier.score(junk, "obj", run_sandbox=False)  # type: ignore[arg-type]
        assert 0.0 <= out["score"] <= 1.0
        assert isinstance(out["diagnostics"], list)


def test_all_diagnostics_are_strings():
    """The loop pastes these into a prompt; a repr of a dict there is a bug."""
    out = verifier.score(UNDEFINED, "dedupe(items)", run_sandbox=False)
    assert out["diagnostics"]
    assert all(isinstance(d, str) for d in out["diagnostics"])


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------


@needs_ruff
def test_lint_clean_code_scores_one():
    out = verifier.lint(GOOD)
    assert out["applicable"] is True
    assert out["score"] == 1.0
    assert out["diagnostics"] == []


@needs_ruff
def test_lint_undefined_name_is_critical_zero():
    out = verifier.lint(UNDEFINED)
    assert out["score"] == 0.0
    assert any("F821" in d for d in out["diagnostics"])
    assert any("critical" in d for d in out["diagnostics"])


@needs_ruff
def test_lint_mutable_default_is_major_not_fatal():
    out = verifier.lint("def f(acc=[]):\n    acc.append(1)\n    return acc\n")
    assert 0.0 < out["score"] < 1.0
    assert any("B006" in d for d in out["diagnostics"])


@needs_ruff
def test_lint_unused_import_is_only_a_minor_deduction():
    out = verifier.lint("import os\n\n\ndef f():\n    return 1\n")
    assert out["score"] > 0.85
    assert any("F401" in d for d in out["diagnostics"])


@needs_ruff
def test_lint_catches_a_bug_execution_cannot_see():
    """The whole reason lint is weighted: an unreached branch.

    The smoke call takes the `if items:` path and returns fine; the else
    branch references a name that does not exist. Execution says "works".
    """
    code = "def f(items):\n    if items:\n        return items[0]\n    return fallback_value\n"
    assert verifier.lint(code)["score"] == 0.0


def test_lint_unavailable_scores_zero_rather_than_passing(monkeypatch):
    """A signal that cannot be computed is 0 and says so — never a free pass.

    core/confidence.py's `security_clean` defaulted to 1.0 whenever it could
    not tell, which is how `def solve(n): pass` scored 1.000.
    """
    monkeypatch.setattr(verifier, "_ruff_bin", lambda: None)
    out = verifier.lint(GOOD)
    assert out["score"] == 0.0
    assert out["applicable"] is False
    assert any("ruff is not installed" in d for d in out["diagnostics"])


# ---------------------------------------------------------------------------
# signature analysis (no sandbox needed)
# ---------------------------------------------------------------------------


def test_target_prefers_the_function_the_objective_names():
    code = "def helper(x):\n    return x\n\n\ndef solve(n):\n    return helper(n)\n"
    assert verifier.target_function(code, "implement solve(n)").name == "solve"


def test_target_prefers_an_entry_point_over_a_helper():
    code = (
        "def helper(x):\n    return x + 1\n\n\n"
        "def main(xs):\n    return [helper(x) for x in xs]\n"
    )
    assert verifier.target_function(code, "no name here").name == "main"


def test_target_is_none_without_a_function():
    assert verifier.target_function("x = 1\nprint(x)\n", "") is None


def test_arg_tuples_follow_annotations():
    func = ast.parse("def f(n: int, xs: list[str]) -> int:\n    return n\n").body[0]
    tuples = verifier.arg_tuples(func)
    assert tuples[0] == ["5", "[3, 1, 2]"]


def test_arg_tuples_skip_parameters_that_have_defaults():
    func = ast.parse("def f(xs, reverse=False):\n    return xs\n").body[0]
    assert len(verifier.arg_tuples(func)[0]) == 1


def test_arg_tuples_guess_from_parameter_names_without_annotations():
    func = ast.parse("def f(text):\n    return text\n").body[0]
    assert verifier.arg_tuples(func)[0] == ['"hello world"']


def test_generated_inputs_are_identical_for_the_same_seed():
    a = verifier.generate_inputs(GOOD, "dedupe(items)", n=5, seed=7)
    b = verifier.generate_inputs(GOOD, "dedupe(items)", n=5, seed=7)
    assert a == b and len(a) == 5


def test_idempotence_is_only_required_when_the_prose_asks():
    func = verifier.target_function(GOOD, "dedupe")
    assert verifier._wants_idempotence("normalise the list", func) is False
    assert verifier._wants_idempotence("must be idempotent", func) is True


# ---------------------------------------------------------------------------
# execution + properties (sandbox)
# ---------------------------------------------------------------------------


@needs_sandbox
def test_correct_code_scores_near_one():
    out = verifier.score(GOOD, "write dedupe(items) preserving order")
    assert out["score"] > 0.9
    assert out["signals"]["executes"] == 1.0
    assert out["signals"]["properties"] == 1.0
    assert out["coverage"] == 1.0


@needs_sandbox
def test_argument_mutation_is_detected_and_reported():
    out = verifier.score(MUTATES, "write dedupe(items) preserving order")
    assert out["signals"]["properties"] < 1.0
    assert any("no_mutation" in d and "FAILED" in d for d in out["diagnostics"])
    assert out["score"] < verifier.score(GOOD, "write dedupe(items)")["score"]


@needs_sandbox
def test_a_crashing_smoke_call_costs_half_the_execution_signal():
    out = verifier.score(CRASHES, "dedupe(items)")
    assert out["signals"]["executes"] == 0.5  # module ran, call did not
    assert any("IndexError" in d for d in out["diagnostics"])


@needs_sandbox
def test_module_level_failure_is_reported_not_swallowed():
    out = verifier.score("raise SystemExit(3)\n", "anything")
    assert out["signals"]["executes"] == 0.0
    assert any("module body failed" in d for d in out["diagnostics"])


@needs_sandbox
def test_a_self_assertion_that_fails_does_not_hide_the_rest():
    """The candidate's own failing assert must not abort the probe.

    core/holdout.py had to strip these for the same reason. Here we still see
    the module-level failure AND keep a usable diagnostic.
    """
    code = GOOD + "\nassert dedupe([1, 1]) == [1, 1]\n"
    out = verifier.score(code, "dedupe(items)")
    assert any("AssertionError" in d for d in out["diagnostics"])
    assert out["score"] < 1.0


@needs_sandbox
def test_empty_input_crash_is_a_property_failure():
    code = "def first(items):\n    return items[0]\n"
    out = verifier.score(code, "first(items) returns the first element")
    assert any("empty_input" in d and "FAILED" in d for d in out["diagnostics"])


@needs_sandbox
def test_deliberate_rejection_of_empty_input_is_not_a_failure():
    code = (
        "def mean(values):\n"
        "    if not values:\n"
        "        raise ValueError('empty')\n"
        "    return sum(values) / len(values)\n"
    )
    out = verifier.score(code, "mean(values)")
    assert any("empty_input: ok" in d for d in out["diagnostics"])


@needs_sandbox
def test_return_type_annotation_is_checked():
    code = "def count(items) -> int:\n    return [len(items)]\n"
    out = verifier.score(code, "count(items) -> int")
    assert any("return_type" in d and "FAILED" in d for d in out["diagnostics"])


@needs_sandbox
def test_properties_report_unverified_rather_than_passing():
    """No derivable property must read as 'unverified', never as 'ok'."""
    code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    out = verifier.score(code, "add two ints")
    # return_type IS derivable here, so the property signal is live and passes;
    # what must never happen is a property signal that is 1.0 with nothing
    # actually checked.
    assert out["applicable"]["properties"] is True
    assert any("return_type: ok" in d for d in out["diagnostics"])


@needs_sandbox
def test_code_with_no_function_is_uncovered_not_perfect():
    out = verifier.score("x = sum([1, 2, 3])\nprint(x)\n", "add some numbers")
    assert out["coverage"] < 1.0
    assert out["score"] < 0.8
    assert any("no module-level function" in d for d in out["diagnostics"])


@needs_sandbox
def test_probe_failure_scores_zero_and_explains(monkeypatch):
    monkeypatch.setattr(
        verifier, "_run_probe", lambda program, timeout: {
            "ok": False, "data": {}, "error": "sandbox unavailable: boom",
            "stdout": "", "stderr": "",
        }
    )
    out = verifier.score(GOOD, "dedupe(items)")
    assert out["signals"]["executes"] == 0.0
    assert out["signals"]["properties"] == 0.0
    assert any("sandbox unavailable" in d for d in out["diagnostics"])


@needs_sandbox
def test_infinite_loop_does_not_hang_the_verifier():
    out = verifier.score("def spin(n):\n    while True:\n        n += 1\n", "spin(n)", timeout=5)
    assert out["signals"]["executes"] < 1.0


# ---------------------------------------------------------------------------
# self-consistency
# ---------------------------------------------------------------------------


@needs_sandbox
def test_consistency_ranks_the_odd_one_out_last():
    a = "def top_two(nums):\n    return sorted(nums, reverse=True)[:2]\n"
    b = "def top_two(nums):\n    return sorted(nums)[-2:][::-1]\n"
    c = "def top_two(nums):\n    return nums[:2]\n"
    out = verifier.consistency([a, b, c], "top_two(nums) returns the two largest")
    assert out["applicable"] is True
    assert out["scores"][0] > out["scores"][2]
    assert out["scores"][1] > out["scores"][2]


@needs_sandbox
def test_consistency_uses_identical_inputs_for_every_candidate():
    a = "def f(n):\n    return n * 2\n"
    b = "def f(n):\n    return n + n\n"
    out = verifier.consistency([a, b], "f(n) doubles n")
    assert out["outputs"][0] == out["outputs"][1]
    assert out["scores"][0] == out["scores"][1] == 1.0


def test_consistency_of_one_candidate_is_not_a_pass():
    out = verifier.consistency([GOOD], "dedupe(items)")
    assert out["applicable"] is False
    assert out["scores"] == [0.0]
    assert any("cannot corroborate" in d for d in out["diagnostics"])


def test_consistency_never_raises():
    for bad in ([], ["def f(:"], [None, 3], ["", ""]):
        out = verifier.consistency(bad, "obj")  # type: ignore[arg-type]
        assert isinstance(out["scores"], list)
        assert len(out["scores"]) == len(bad)


@needs_sandbox
def test_consistency_gives_agreement_on_an_exception_less_credit_than_a_value():
    """Two candidates that both forget the same guard are not corroborated."""
    a = "def first(items):\n    return items[0]\n"
    b = "def first(items):\n    return list(items)[0]\n"
    out = verifier.consistency([a, b], "first(items)", n_inputs=6, seed=3)
    # They agree everywhere, but some inputs are empty -> both raise.
    assert out["applicable"] is True
    assert all(s < 1.0 for s in out["scores"])


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------


def test_weights_sum_to_one_and_have_a_single_source_each():
    """No signal is counted twice — the core/confidence.py bug.

    There, `security_clean` and `static_analysis_score` were the same bit under
    two names, carrying 0.35 of the weight between them.
    """
    assert round(sum(verifier.DEFAULT_WEIGHTS.values()), 6) == 1.0
    assert len(set(verifier.DEFAULT_WEIGHTS)) == len(verifier.DEFAULT_WEIGHTS)


def test_score_is_bounded_and_reports_every_signal():
    out = verifier.score(GOOD, "dedupe(items)", run_sandbox=False)
    assert set(out["signals"]) == {"parses", "not_stub", "lint", "executes", "properties"}
    assert set(out["applicable"]) == set(out["signals"])
    assert 0.0 <= out["score"] <= 1.0
    assert 0.0 <= out["normalized"] <= 1.0


def test_disabling_the_sandbox_scores_zero_for_execution_not_a_pass():
    out = verifier.score(GOOD, "dedupe(items)", run_sandbox=False)
    assert out["signals"]["executes"] == 0.0
    assert any("execution disabled" in d for d in out["diagnostics"])


def test_a_do_nothing_stub_is_gated_to_zero():
    """`def solve(n): pass` scored 1.000 under the old confidence metric.

    It also passes every *behavioural* signal in this module — it runs, it
    mutates nothing, it survives empty input — which is exactly why it needs a
    structural gate rather than a deduction.
    """
    out = verifier.score("def solve(n):\n    pass\n", "solve(n) returns twice n")
    assert out["score"] == 0.0
    assert out["signals"]["not_stub"] == 0.0
    assert any("implements nothing" in d for d in out["diagnostics"])


@pytest.mark.parametrize(
    "body",
    [
        "    pass",
        "    ...",
        "    return",
        "    return None",
        "    raise NotImplementedError",
        "    raise NotImplementedError('todo')",
        '    """Return twice n."""',
        '    """Return twice n."""\n    pass',
    ],
)
def test_every_shape_of_empty_body_is_a_stub(body):
    func = verifier.target_function(f"def solve(n):\n{body}\n", "solve")
    assert verifier.is_stub(func) is True


@pytest.mark.parametrize(
    "body",
    ["    return n * 2", '    """Doc."""\n    return n * 2', "    raise ValueError('no')"],
)
def test_a_real_body_is_not_a_stub(body):
    func = verifier.target_function(f"def solve(n):\n{body}\n", "solve")
    assert verifier.is_stub(func) is False


def test_forged_test_output_does_not_score_well():
    """`print('42 passed in 0.01s')` also scored 1.000 under the old metric."""
    code = "def solve(n):\n    return None\n\n\nprint('42 passed in 0.01s')\n"
    out = verifier.score(code, "solve(n) returns twice n")
    assert out["score"] == 0.0


@needs_sandbox
def test_a_function_that_computes_nothing_fails_the_returns_value_property():
    """Not a stub structurally, but it still returns None for every input."""
    code = "def solve(items):\n    total = 0\n    for x in items:\n        total += x\n"
    out = verifier.score(code, "solve(items) returns the sum")
    assert any("returns_value" in d and "FAILED" in d for d in out["diagnostics"])
    assert out["score"] < 1.0


@needs_sandbox
def test_returning_none_is_fine_when_the_task_asks_for_an_in_place_change():
    code = "def solve(items):\n    items.sort()\n"
    out = verifier.score(code, "solve(items) sorts the list in place")
    assert not any("returns_value" in d for d in out["diagnostics"])
