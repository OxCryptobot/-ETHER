"""Refuse to send the model the answers it will be graded on.

Held-out grading is only meaningful if the generator never saw the holdout. The
holdout has now leaked through four separate channels:

  1. curriculum objectives that contained the implementation and its asserts
  2. benchmark prompts with the assertions inline
  3. `hidden_quiz.py`'s private grader with no leak check at all
  4. BM25 workspace retrieval indexing `scripts/`, which pulled `bench.py` —
     holdout tests and all — into the prompt. Measured: 12 of 15 bench tasks
     leaked at least one verbatim assertion; five leaked all five.

Each was fixed at its source, and a fifth channel would be found the same way:
by accident, after publishing a number. This module is the check that does not
depend on remembering every channel — it inspects the finished prompt.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def target_symbols(objective: str) -> List[str]:
    """Function and class names the objective asks the model to implement.

    Matches `def name(`, `class Name`, and bare `def name` in prose, since
    objectives state signatures rather than code.
    """
    if not objective:
        return []
    names = re.findall(r"\bdef\s+([A-Za-z_]\w*)", objective)
    names += re.findall(r"\bclass\s+([A-Za-z_]\w*)", objective)
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def defines_target(example: str, objective: str) -> List[str]:
    """Target symbols that `example` already implements.

    Few-shot retrieval on a benchmark is STRUCTURALLY a leak: the store fills
    with solutions to the very tasks being measured, and similarity search then
    surfaces the closest one — which is the answer. Observed directly: the
    retrieved block for `edit_distance` contained `def edit_distance`, and 14
    of 40 tasks had a prior solution sitting in memory/experience/pass.jsonl.

    The assertion check cannot catch this. The holdout never appears; the
    SOLUTION does, so `leaked` reads 0 while the model is handed the answer.
    """
    if not example or not objective:
        return []
    hit = []
    for name in target_symbols(objective):
        if re.search(rf"\b(?:def|class)\s+{re.escape(name)}\b", example):
            hit.append(name)
    return hit


def assertion_lines(holdout_test: str) -> List[str]:
    """The assertion statements a holdout would grade with."""
    return [
        line.strip()
        for line in (holdout_test or "").splitlines()
        if line.strip().startswith("assert ")
    ]


def find_leaks(prompt: str, holdout_test: str) -> List[str]:
    """Holdout assertions that appear in the prompt, verbatim or reflowed."""
    if not (prompt or "").strip() or not (holdout_test or "").strip():
        return []
    haystack = _normalize(prompt)
    leaks = []
    for line in assertion_lines(holdout_test):
        if _normalize(line) in haystack:
            leaks.append(line)
    return leaks


def scrub(prompt: str, holdout_test: str) -> str:
    """Drop retrieved blocks that carry holdout assertions.

    Blocks are separated by blank lines, which matches how the composite prompt
    is assembled from plan / experience / few-shot / repo-map / context
    sections. Only the offending block is removed, so a leak in retrieved
    context does not discard the objective.
    """
    leaks = find_leaks(prompt, holdout_test)
    if not leaks:
        return prompt
    needles = {_normalize(line) for line in leaks}
    kept = []
    for block in re.split(r"\n\s*\n", prompt or ""):
        norm = _normalize(block)
        if any(n in norm for n in needles):
            continue
        kept.append(block)
    return "\n\n".join(kept)


def check(prompt: str, holdout_test: str) -> Dict[str, Any]:
    """Report whether a prompt is clean, and a scrubbed version if not.

    Never raises: a grading run that dies on a leak is worse than one that
    reports the leak and marks its own verdict untrustworthy.
    """
    leaks = find_leaks(prompt, holdout_test)
    return {
        "clean": not leaks,
        "leaks": leaks,
        "leak_count": len(leaks),
        "scrubbed": scrub(prompt, holdout_test) if leaks else prompt,
        "detail": (
            ""
            if not leaks
            else f"{len(leaks)} holdout assertion(s) reached the prompt: {leaks[0][:80]}"
        ),
    }
