"""The model must never be shown the assertions it will be graded on.

The holdout has now leaked through four separate channels: curriculum
objectives containing their own answers, benchmark prompts with assertions
inline, hidden_quiz's private grader with no check at all, and BM25 retrieval
indexing scripts/ — which pulled bench.py, holdout tests and all, into the
prompt. That last one produced a reported pass_rate of 0.933: 12 of 15 tasks
leaked, five of them leaked all five assertions.

Each was closed at its source, and a fifth would have been found the same way —
by accident, after publishing a number. These tests cover the check that does
not depend on enumerating channels.
"""

from __future__ import annotations

from pathlib import Path

from core.prompt_guard import check, find_leaks, scrub

HOLDOUT = "assert is_even(4) is True\nassert is_even(5) is False\nprint('ok')"


def test_clean_prompt_passes():
    prompt = "Implement:\n\ndef is_even(n: int) -> bool\n\nReturn True when n is even."
    assert check(prompt, HOLDOUT)["clean"] is True


def test_verbatim_assertion_is_caught():
    prompt = "Implement is_even.\n\n### context\nassert is_even(4) is True\n"
    result = check(prompt, HOLDOUT)
    assert result["clean"] is False
    assert result["leak_count"] == 1


def test_reflowed_assertion_is_caught():
    """Retrieval reflows whitespace; matching must survive that."""
    prompt = "ctx:\n    assert   is_even(4)   is   True\n"
    assert check(prompt, HOLDOUT)["clean"] is False


def test_assertion_inside_a_string_literal_is_caught():
    """The two surviving bench leaks were holdouts embedded in core/ source."""
    prompt = 'ctx:\n    "assert is_even(4) is True\\n"\n'
    assert check(prompt, HOLDOUT)["clean"] is False


def test_scrub_removes_only_the_offending_block():
    prompt = (
        "Implement:\n\ndef is_even(n: int) -> bool\n\n"
        "### repo context\nassert is_even(4) is True\n\n"
        "### keep me\nsomething useful\n"
    )
    cleaned = scrub(prompt, HOLDOUT)
    assert check(cleaned, HOLDOUT)["clean"] is True
    assert "def is_even(n: int) -> bool" in cleaned
    assert "keep me" in cleaned


def test_no_holdout_means_nothing_to_leak():
    assert check("anything at all", "")["clean"] is True
    assert find_leaks("anything", "") == []


def test_guard_never_raises_on_odd_input():
    for prompt, holdout in [("", ""), (None, HOLDOUT), ("x", None)]:
        assert isinstance(check(prompt or "", holdout or ""), dict)


def test_bench_prompts_do_not_leak_through_retrieval():
    """End-to-end: the real context assembler against the real bench tasks.

    Before the SKIP fix this failed for 12 of 15 tasks.
    """
    import scripts.bench as bench
    from core.context import gather_workspace_context

    leaking = []
    for task in bench.load_tasks():
        context = gather_workspace_context(Path("."), query=task["objective"]) or ""
        guarded = check(context, task["holdout_test"])
        if not guarded["clean"]:
            # The guard must at least be able to clean it.
            assert check(guarded["scrubbed"], task["holdout_test"])["clean"] is True
            leaking.append(task["id"])
    # Retrieval itself should be clean for the overwhelming majority; the guard
    # is the backstop for assertions embedded in core/ source.
    assert len(leaking) <= 3, f"retrieval leak regression: {leaking}"
