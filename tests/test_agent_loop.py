"""Tests for core/agent_loop.py.

Every test here pins a property that `docs/FINDINGS.md` measured the old
pipeline getting wrong. No model is called: `generate_fn` is injected and the
verifier is faked except in the two integration tests at the bottom, which use
the real one and skip if the sandbox is unavailable.
"""

from __future__ import annotations

import pytest

from core import verifier
from core.agent_loop import (
    Attempt,
    HoldoutLeak,
    LoopBudget,
    assert_no_holdout,
    build_repair_prompt,
    estimate_tokens,
    extract_code,
    run_loop,
)


def _sandbox_works() -> bool:
    run = verifier._run_probe(verifier._build_probe("x = 1\n", "", [], {}), timeout=30)
    return bool(run["ok"])


SANDBOX_OK = _sandbox_works()
needs_sandbox = pytest.mark.skipif(not SANDBOX_OK, reason="no working sandbox")

GOOD = """def dedupe(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out"""

MUTATES = """def dedupe(items):
    items.sort()
    return sorted(set(items))"""

BROKEN = """def dedupe(items):
    return mystery_helper(items)"""


def fixed_generator(outputs):
    """A generate_fn that replays canned model output, recording its prompts."""
    calls = []

    def gen(prompt, temperature, seed):
        calls.append({"prompt": prompt, "temperature": temperature, "seed": seed})
        return outputs[min(len(calls) - 1, len(outputs) - 1)]

    gen.calls = calls  # type: ignore[attr-defined]
    return gen


def scores_from(mapping, default=0.0):
    """A fake score_fn keyed by a substring of the candidate code."""

    def score_fn(code, objective=""):
        value = default
        for needle, v in mapping.items():
            if needle in code:
                value = v
                break
        return {
            "score": value,
            "normalized": value,
            "coverage": 1.0,
            "signals": {"executes": value},
            "applicable": {"executes": True},
            "diagnostics": [f"fake verifier scored {value}"],
        }

    return score_fn


# ---------------------------------------------------------------------------
# code extraction — FINDINGS §3: unstripped fences reached the sandbox as
# Python and errored 10 of 120 samples that the bare call never lost.
# ---------------------------------------------------------------------------


def test_extract_plain_code_unchanged():
    assert extract_code(GOOD).strip() == GOOD.strip()


def test_extract_fenced_python():
    assert extract_code(f"```python\n{GOOD}\n```") == GOOD


def test_extract_fenced_without_language_tag():
    assert extract_code(f"```\n{GOOD}\n```") == GOOD


def test_extract_with_prose_preamble_and_epilogue():
    text = f"Sure! Here's the code:\n\n```python\n{GOOD}\n```\n\nThis preserves order."
    assert extract_code(text) == GOOD


def test_extract_unterminated_fence():
    """A truncated completion leaves the closing fence off."""
    assert extract_code(f"Here you go:\n```python\n{GOOD}") == GOOD


def test_extract_prose_without_any_fence():
    text = f"Here's the code:\n\n{GOOD}\n\nHope that helps!"
    got = extract_code(text)
    assert got.startswith("def dedupe")
    assert "Hope that helps" not in got
    compile(got, "<extracted>", "exec")


def test_extract_ignores_a_shell_block_and_takes_the_python_one():
    text = f"Install nothing:\n```bash\npip install foo\n```\nThen:\n```python\n{GOOD}\n```"
    assert extract_code(text) == GOOD


def test_extract_joins_multiple_python_blocks():
    text = (
        "First a helper:\n```python\ndef helper(x):\n    return x\n```\n"
        "Then:\n```python\ndef main(xs):\n    return [helper(x) for x in xs]\n```"
    )
    got = extract_code(text)
    assert "def helper" in got and "def main" in got
    compile(got, "<extracted>", "exec")


def test_extract_drops_a_reasoning_scratchpad():
    text = f"<think>I should sort it. No, use a set.</think>\n```python\n{GOOD}\n```"
    got = extract_code(text)
    assert "I should sort it" not in got
    assert got == GOOD


def test_extract_handles_an_unclosed_think_tag():
    text = f"<think>mumble mumble</think>{GOOD}"
    assert extract_code(text).strip().startswith("def dedupe")


def test_extract_dedents_a_wholly_indented_answer():
    indented = "\n".join("    " + line for line in GOOD.splitlines())
    got = extract_code(indented)
    compile(got, "<extracted>", "exec")


def test_extract_of_empty_or_prose_only_output():
    assert extract_code("") == ""
    assert extract_code(None) == ""  # type: ignore[arg-type]
    assert "sorry" in extract_code("I'm sorry, I can't help with that.").lower()


def test_extract_returns_something_the_verifier_can_diagnose():
    """Unparseable output is returned, not discarded — the loop needs the error."""
    got = extract_code("```python\ndef f(:\n    pass\n```")
    assert "def f(:" in got


def test_extraction_result_is_what_gets_verified_and_returned():
    gen = fixed_generator([f"Here:\n```python\n{GOOD}\n```"])
    result = run_loop(
        "dedupe", gen, budget=LoopBudget(max_attempts=1), score_fn=scores_from({}, 1.0)
    )
    assert result.code == GOOD
    assert "```" not in result.code


# ---------------------------------------------------------------------------
# budget — attempts AND wall clock AND tokens
# ---------------------------------------------------------------------------


def test_attempt_budget_binds():
    gen = fixed_generator([BROKEN])
    result = run_loop(
        "obj", gen, budget=LoopBudget(max_attempts=3), score_fn=scores_from({}, 0.1)
    )
    assert result.attempts_used == 3
    assert "attempt budget" in result.stop_reason


def test_wall_clock_budget_binds_before_the_attempt_budget():
    import time

    def slow(prompt, temperature, seed):
        time.sleep(0.05)
        return BROKEN

    result = run_loop(
        "obj",
        slow,
        budget=LoopBudget(max_attempts=50, wall_clock_s=0.12),
        score_fn=scores_from({}, 0.1),
    )
    assert result.attempts_used < 50
    assert "wall clock" in result.stop_reason


def test_token_budget_binds():
    gen = fixed_generator(["x = 1\n" + "# padding\n" * 400])
    result = run_loop(
        "obj",
        gen,
        budget=LoopBudget(max_attempts=10, max_tokens=1200),
        score_fn=scores_from({}, 0.1),
    )
    assert "token budget" in result.stop_reason
    assert result.tokens_used >= 1200


def test_token_accounting_counts_prompt_and_completion():
    gen = fixed_generator([GOOD])
    result = run_loop(
        "obj", gen, budget=LoopBudget(max_attempts=1), score_fn=scores_from({}, 0.5)
    )
    a = result.attempts[0]
    assert a.tokens == estimate_tokens(a.prompt) + estimate_tokens(a.raw_output)
    assert result.tokens_used == a.tokens


def test_a_custom_token_counter_is_used():
    gen = fixed_generator([GOOD])
    result = run_loop(
        "obj",
        gen,
        budget=LoopBudget(max_attempts=1),
        score_fn=scores_from({}, 0.5),
        token_counter=lambda t: 7,
    )
    assert result.attempts[0].tokens == 14


# ---------------------------------------------------------------------------
# NEVER REGRESS — FINDINGS §1: the pipeline overwrites attempt 1 with attempt
# 2 unconditionally, and on the 35B run that cost a task.
# ---------------------------------------------------------------------------


def test_a_worse_second_attempt_is_not_selected():
    gen = fixed_generator([GOOD, BROKEN])
    result = run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=2),
        score_fn=scores_from({"seen": 0.8, "mystery_helper": 0.1}),
        consistency_weight=0.0,
        confidence_threshold=0.99,
    )
    assert result.attempts_used == 2
    assert result.selected_index == 0
    assert result.code == GOOD
    assert "beat #1=0.100" in result.selection_reason


def test_a_better_second_attempt_is_selected():
    gen = fixed_generator([BROKEN, GOOD])
    result = run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=2),
        score_fn=scores_from({"seen": 0.8, "mystery_helper": 0.1}),
        consistency_weight=0.0,
        confidence_threshold=0.99,
    )
    assert result.selected_index == 1
    assert result.code == GOOD


def test_the_worst_attempt_is_never_returned_however_late_it_arrives():
    outputs = [GOOD, MUTATES, BROKEN, BROKEN]
    gen = fixed_generator(outputs)
    result = run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=4),
        score_fn=scores_from({"seen": 0.8, "items.sort": 0.5, "mystery_helper": 0.1}),
        consistency_weight=0.0,
        confidence_threshold=0.99,
    )
    assert result.code == GOOD
    assert result.score == 0.8


def test_ties_go_to_the_earlier_attempt():
    """A later attempt must actually BEAT the incumbent, not merely match it."""
    gen = fixed_generator([GOOD, MUTATES])
    result = run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=2),
        score_fn=scores_from({}, 0.5),
        consistency_weight=0.0,
        confidence_threshold=0.99,
    )
    assert result.selected_index == 0


def test_every_attempt_is_kept_for_audit():
    gen = fixed_generator([GOOD, MUTATES, BROKEN])
    result = run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=3),
        score_fn=scores_from({"seen": 0.8, "items.sort": 0.5, "mystery_helper": 0.1}),
        consistency_weight=0.0,
        confidence_threshold=0.99,
    )
    assert [a.index for a in result.attempts] == [0, 1, 2]
    assert [a.score for a in result.attempts] == [0.8, 0.5, 0.1]
    assert all(a.diagnostics for a in result.attempts)
    audit = result.to_dict()
    assert len(audit["attempts"]) == 3
    assert audit["selected_index"] == 0
    assert audit["selection_reason"]
    assert audit["stop_reason"]


# ---------------------------------------------------------------------------
# iterate on the verifier, not on crashes — FINDINGS §5
# ---------------------------------------------------------------------------


def test_a_clean_exit_with_a_low_score_still_triggers_another_attempt():
    """The measured bug: repair only fired on a non-zero exit, and a wrong
    answer runs fine. Here every candidate 'runs'; only the score is low."""
    gen = fixed_generator([MUTATES, MUTATES, MUTATES])
    result = run_loop(
        "dedupe", gen, budget=LoopBudget(max_attempts=3), score_fn=scores_from({}, 0.5)
    )
    assert result.attempts_used == 3


def test_the_loop_stops_early_when_the_verifier_is_confident():
    gen = fixed_generator([GOOD, BROKEN])
    result = run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=4),
        score_fn=scores_from({}, 0.95),
        confidence_threshold=0.9,
    )
    assert result.attempts_used == 1
    assert "verifier confident" in result.stop_reason


def test_high_confidence_over_thin_coverage_does_not_stop_the_loop():
    """normalized 1.0 across two of four signals is not confidence."""

    def thin(code, objective=""):
        return {
            "score": 0.7,
            "normalized": 1.0,
            "coverage": 0.7,
            "signals": {},
            "applicable": {},
            "diagnostics": ["only lint and execution were live"],
        }

    gen = fixed_generator([GOOD])
    result = run_loop(
        "dedupe", gen, budget=LoopBudget(max_attempts=3), score_fn=thin, min_coverage=0.75
    )
    assert result.attempts_used == 3


# ---------------------------------------------------------------------------
# temperature / diversity
# ---------------------------------------------------------------------------


def test_temperature_rises_across_attempts():
    gen = fixed_generator([BROKEN])
    run_loop("obj", gen, budget=LoopBudget(max_attempts=4), score_fn=scores_from({}, 0.1))
    temps = [c["temperature"] for c in gen.calls]
    assert temps == [0.2, 0.7, 0.9, 1.0]
    assert temps[0] < temps[-1]


def test_temperature_schedule_is_configurable_and_never_runs_out():
    gen = fixed_generator([BROKEN])
    run_loop(
        "obj",
        gen,
        budget=LoopBudget(max_attempts=4),
        temperatures=[0.0, 0.5],
        score_fn=scores_from({}, 0.1),
    )
    assert [c["temperature"] for c in gen.calls] == [0.0, 0.5, 0.5, 0.5]


def test_each_attempt_gets_a_distinct_seed():
    gen = fixed_generator([BROKEN])
    run_loop(
        "obj", gen, budget=LoopBudget(max_attempts=3), seed=100, score_fn=scores_from({}, 0.1)
    )
    assert [c["seed"] for c in gen.calls] == [100, 101, 102]


def test_a_positional_only_generator_still_works():
    seen = []

    def positional(prompt, temperature, seed, /):
        seen.append(temperature)
        return GOOD

    result = run_loop(
        "obj", positional, budget=LoopBudget(max_attempts=1), score_fn=scores_from({}, 0.5)
    )
    assert seen == [0.2]
    assert result.code == GOOD


# ---------------------------------------------------------------------------
# feed back what actually ran — FINDINGS §8
# ---------------------------------------------------------------------------


def test_the_repair_prompt_contains_the_exact_source_that_ran():
    gen = fixed_generator([f"```python\n{MUTATES}\n```", GOOD])
    run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=2),
        score_fn=scores_from({}, 0.5),
        confidence_threshold=0.99,
    )
    repair = gen.calls[1]["prompt"]
    assert MUTATES in repair
    assert "```" not in repair  # the fence never reaches the model again
    assert "EXACT source that was executed" in repair


def test_the_repair_prompt_contains_the_real_diagnostics():
    gen = fixed_generator([MUTATES, GOOD])

    def score_fn(code, objective=""):
        return {
            "score": 0.5,
            "normalized": 0.5,
            "coverage": 1.0,
            "signals": {"executes": 0.5},
            "applicable": {"executes": True},
            "diagnostics": ["property no_mutation: FAILED — arguments were mutated"],
        }

    run_loop("dedupe", gen, budget=LoopBudget(max_attempts=2), score_fn=score_fn)
    assert "no_mutation: FAILED" in gen.calls[1]["prompt"]


def test_repair_is_based_on_the_best_attempt_not_the_last():
    gen = fixed_generator([MUTATES, BROKEN, GOOD])
    run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=3),
        score_fn=scores_from({"items.sort": 0.6, "mystery_helper": 0.1}, 0.6),
        confidence_threshold=0.99,
    )
    third = gen.calls[2]["prompt"]
    assert MUTATES in third
    assert "mystery_helper" not in third


def test_a_hopeless_candidate_is_resampled_rather_than_patched():
    gen = fixed_generator([BROKEN, GOOD])
    result = run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=2),
        score_fn=scores_from({"mystery_helper": 0.05}, 0.9),
        confidence_threshold=0.99,
    )
    assert result.attempts[1].kind == "resample"
    assert "take another approach" in gen.calls[1]["prompt"]


def test_build_repair_prompt_survives_an_attempt_with_no_diagnostics():
    bare = Attempt(index=0, kind="initial", temperature=0.2, seed=1, code="x = 1")
    prompt = build_repair_prompt("obj", bare)
    assert "no diagnostics" in prompt


# ---------------------------------------------------------------------------
# holdout hygiene — FINDINGS §2
# ---------------------------------------------------------------------------

HOLDOUT = "assert dedupe([1, 1, 2]) == [1, 2]\nassert dedupe([]) == []\n"


def test_the_holdout_never_appears_in_any_prompt():
    gen = fixed_generator([MUTATES, MUTATES, MUTATES])
    result = run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=3),
        holdout_test=HOLDOUT,
        score_fn=scores_from({}, 0.5),
    )
    assert len(gen.calls) == 3
    for call in gen.calls:
        assert "dedupe([1, 1, 2])" not in call["prompt"]
        assert "assert dedupe" not in call["prompt"]
    for attempt in result.attempts:
        assert "assert dedupe" not in attempt.prompt
        assert not any("assert dedupe" in d for d in attempt.diagnostics)


def test_passing_a_holdout_changes_no_decision():
    """Selection must be identical with and without it — it scores, it does not steer."""
    kwargs = dict(
        budget=LoopBudget(max_attempts=3),
        score_fn=scores_from({"seen": 0.8, "items.sort": 0.5, "mystery_helper": 0.1}),
        consistency_weight=0.0,
        confidence_threshold=0.99,
    )
    without = run_loop("dedupe", fixed_generator([MUTATES, GOOD, BROKEN]), **kwargs)
    with_holdout = run_loop(
        "dedupe", fixed_generator([MUTATES, GOOD, BROKEN]), holdout_test=HOLDOUT, **kwargs
    )
    assert without.selected_index == with_holdout.selected_index
    assert without.code == with_holdout.code
    assert without.score == with_holdout.score
    assert [a.prompt for a in without.attempts] == [a.prompt for a in with_holdout.attempts]


def test_a_leaking_context_raises_rather_than_producing_a_void_number():
    gen = fixed_generator([GOOD])
    with pytest.raises(HoldoutLeak):
        run_loop(
            "dedupe",
            gen,
            budget=LoopBudget(max_attempts=1),
            holdout_test=HOLDOUT,
            extra_context="For reference: " + HOLDOUT,
            score_fn=scores_from({}, 0.5),
        )


def test_assert_no_holdout_catches_a_single_leaked_assertion():
    with pytest.raises(HoldoutLeak):
        assert_no_holdout("do this: assert dedupe([1, 1, 2]) == [1, 2]", HOLDOUT)
    assert_no_holdout("write a dedupe function", HOLDOUT)
    assert_no_holdout("anything at all", "")


def test_holdout_grading_reports_without_influencing(monkeypatch):
    graded = {}

    def fake_grade(code, hidden_test, timeout=60):
        graded["code"] = code
        return {"ok": True, "reason": ""}

    import core.holdout as holdout_mod

    monkeypatch.setattr(holdout_mod, "grade_against_holdout", fake_grade)
    result = run_loop(
        "dedupe",
        fixed_generator([GOOD]),
        budget=LoopBudget(max_attempts=1),
        holdout_test=HOLDOUT,
        score_fn=scores_from({}, 0.5),
    )
    assert result.holdout_ok is True
    assert graded["code"] == result.code


# ---------------------------------------------------------------------------
# robustness — the loop must not be the thing that loses a sample
# ---------------------------------------------------------------------------


def test_a_generator_that_raises_is_recorded_and_the_loop_continues():
    calls = {"n": 0}

    def flaky(prompt, temperature, seed):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("ollama timed out")
        return GOOD

    result = run_loop(
        "dedupe", flaky, budget=LoopBudget(max_attempts=3), score_fn=scores_from({}, 0.95)
    )
    assert "ollama timed out" in result.attempts[0].error
    assert result.code == GOOD
    assert result.selected_index == 1


def test_a_verifier_that_raises_does_not_take_the_loop_down():
    def exploding(code, objective=""):
        raise ValueError("boom")

    result = run_loop(
        "dedupe", fixed_generator([GOOD]), budget=LoopBudget(max_attempts=1), score_fn=exploding
    )
    assert result.attempts[0].score == 0.0
    assert any("boom" in d for d in result.attempts[0].diagnostics)


def test_output_with_no_code_is_recorded_not_selected():
    gen = fixed_generator(["I cannot help with that.", GOOD])
    result = run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=2),
        score_fn=scores_from({"seen": 0.9}, 0.0),
        confidence_threshold=0.99,
    )
    assert result.code == GOOD


def test_a_run_that_produces_nothing_returns_an_empty_result_not_an_exception():
    result = run_loop(
        "dedupe",
        fixed_generator([""]),
        budget=LoopBudget(max_attempts=2),
        score_fn=scores_from({}, 0.0),
    )
    assert result.code == ""
    assert result.selected_index == -1
    assert result.selection_reason == "no candidate produced"


def test_an_on_attempt_callback_that_raises_is_contained():
    def boom(attempt):
        raise RuntimeError("dashboard down")

    result = run_loop(
        "dedupe",
        fixed_generator([GOOD]),
        budget=LoopBudget(max_attempts=1),
        score_fn=scores_from({}, 0.9),
        on_attempt=boom,
    )
    assert result.code == GOOD


# ---------------------------------------------------------------------------
# best-of-N with self-consistency
# ---------------------------------------------------------------------------


def test_consistency_shifts_selection_between_equally_scored_candidates():
    a = "def f(n):\n    return n * 2\n"
    b = "def f(n):\n    return n + n\n"
    c = "def f(n):\n    return n * 3\n"
    gen = fixed_generator([c, a, b])

    def cons(codes, objective=""):
        # c is the odd one out; a and b corroborate each other.
        order = {code: i for i, code in enumerate(codes)}
        scores = [0.0] * len(codes)
        for code, i in order.items():
            scores[i] = 0.1 if "n * 3" in code else 0.9
        return {"scores": scores, "applicable": True, "diagnostics": []}

    result = run_loop(
        "double n",
        gen,
        budget=LoopBudget(max_attempts=3),
        score_fn=scores_from({}, 0.6),
        consistency_fn=cons,
        consistency_weight=0.25,
        confidence_threshold=0.99,
    )
    assert "n * 3" not in result.code
    assert result.selected_index == 1  # earliest of the two corroborated draws


def test_consistency_that_cannot_be_computed_does_not_change_the_ranking():
    def cons(codes, objective=""):
        return {"scores": [0.0] * len(codes), "applicable": False, "diagnostics": ["nope"]}

    gen = fixed_generator([GOOD, BROKEN])
    result = run_loop(
        "dedupe",
        gen,
        budget=LoopBudget(max_attempts=2),
        score_fn=scores_from({"seen": 0.8, "mystery_helper": 0.1}),
        consistency_fn=cons,
        confidence_threshold=0.99,
    )
    assert result.selected_index == 0
    assert result.score == 0.8


def test_a_consistency_fn_that_raises_is_contained():
    def cons(codes, objective=""):
        raise RuntimeError("sandbox gone")

    result = run_loop(
        "dedupe",
        fixed_generator([GOOD, BROKEN]),
        budget=LoopBudget(max_attempts=2),
        score_fn=scores_from({"seen": 0.8, "mystery_helper": 0.1}),
        consistency_fn=cons,
        confidence_threshold=0.99,
    )
    assert result.selected_index == 0


# ---------------------------------------------------------------------------
# integration: the real verifier, no model
# ---------------------------------------------------------------------------


@needs_sandbox
def test_real_verifier_keeps_the_good_first_attempt_over_a_broken_repair():
    """The regression FINDINGS §1 measured, reproduced end to end.

    Attempt 1 works but mutates its argument (0.85 — below the confidence
    threshold, so the loop tries again). Attempt 2 is a plausible-looking
    rewrite with an undefined name. The old pipeline would have returned
    attempt 2. This must return attempt 1.
    """
    gen = fixed_generator([f"```python\n{MUTATES}\n```", f"```python\n{BROKEN}\n```"])
    result = run_loop(
        "write dedupe(items) that removes duplicates preserving order",
        gen,
        budget=LoopBudget(max_attempts=2),
    )
    assert result.attempts_used == 2
    assert result.attempts[0].score > result.attempts[1].score
    assert result.selected_index == 0
    assert result.code == MUTATES


@needs_sandbox
def test_real_verifier_takes_the_improved_repair():
    gen = fixed_generator([f"```python\n{MUTATES}\n```", f"```python\n{GOOD}\n```"])
    result = run_loop(
        "write dedupe(items) that removes duplicates preserving order",
        gen,
        budget=LoopBudget(max_attempts=3),
    )
    assert result.selected_index == 1
    assert result.code == GOOD
    assert "verifier confident" in result.stop_reason


@needs_sandbox
def test_real_verifier_never_scores_a_do_nothing_stub_above_a_real_answer():
    stub = "def dedupe(items):\n    pass\n"
    gen = fixed_generator([f"```python\n{stub}\n```", f"```python\n{GOOD}\n```"])
    result = run_loop(
        "write dedupe(items) preserving order", gen, budget=LoopBudget(max_attempts=2)
    )
    assert result.code == GOOD
