#!/usr/bin/env python3
"""Regression bench — --fast (5) or full (15).

WHAT THIS MEASURES, AND WHAT IT USED TO MEASURE
-----------------------------------------------
Every prompt in this file used to read, literally:

    Write only Python: def is_even(n):
        return n % 2 == 0
    assert is_even(4) and not is_even(5)
    print(is_even(4))

The prompt contained the finished implementation *and* the assertion it would
be graded on, and the pass criterion was `status == "complete" and exit_code
== 0`. A model that copied the prompt back scored 1.000 on all 15 tasks, which
is exactly what `memory/bench/latest.json` recorded. That number is the input
to `core/bench_guardian.py`'s baseline ratchet and to
`core/health_metric.declare_healthy()`, so the system's primary health signal
was measuring transcription.

The repaired shape mirrors `memory/curriculum/tiers.json`:

  * `objective` states a signature and describes the behaviour. No body, no
    assertions.
  * `holdout_test` carries the assertions. The generator never sees them; they
    are appended after generation by `core.holdout.grade_against_holdout`,
    which also strips the model's own module-level asserts and requires an
    unpredictable sentinel on stdout, so `sys.exit(0)` cannot fake a pass.

A task passes when the HOLDOUT passes. Exit code 0 is still reported, for
diagnosis, but is no longer by itself evidence of anything.

Task order and count are unchanged, so `--fast` still runs the same first five
problems and historical `bench_*.json` rows remain comparable by `i` / title.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv
from core.pipeline import Pipeline
from core.health_metric import compute_health
from core.bench_guardian import evaluate as guardian_evaluate
from core.curriculum import check_task_leakage
from core.holdout import grade_against_holdout
from core.scoreboard import write_scoreboard

load_dotenv(ROOT / ".env")

FAST_N = 5

PREAMBLE = "Write only Python, no markdown.\n\nImplement:\n\n"

# id/title are stable: the nth task here is the nth task of every historical
# bench run, so pass_rate before and after this fix compares like for like
# (what changed is what is asked, and how it is graded).
BENCH_TASKS: List[Dict[str, str]] = [
    {
        "id": "b01",
        "title": "is_even",
        "objective": (
            PREAMBLE + "def is_even(n: int) -> bool\n\n"
            "Return the bool True when n is an even integer and False otherwise. "
            "Zero counts as even, and negative even numbers are even."
        ),
        "holdout_test": (
            "assert is_even(4) is True\n"
            "assert is_even(5) is False\n"
            "assert is_even(0) is True\n"
            "assert is_even(-2) is True\n"
            "assert is_even(-3) is False\n"
            "print('ok')"
        ),
    },
    {
        "id": "b02",
        "title": "add",
        "objective": (
            PREAMBLE + "def add(a, b)\n\n"
            "Return the sum of the two numbers. Works for ints and floats."
        ),
        "holdout_test": (
            "assert add(2, 3) == 5\n"
            "assert add(-1, 1) == 0\n"
            "assert add(0, 0) == 0\n"
            "assert add(2.5, 0.5) == 3.0\n"
            "print('ok')"
        ),
    },
    {
        "id": "b03",
        "title": "reverse_string",
        "objective": (
            PREAMBLE + "def reverse_string(s: str) -> str\n\n"
            "Return the characters of s in reverse order. "
            "An empty string returns an empty string."
        ),
        "holdout_test": (
            "assert reverse_string('abc') == 'cba'\n"
            "assert reverse_string('') == ''\n"
            "assert reverse_string('a') == 'a'\n"
            "assert reverse_string('ab cd') == 'dc ba'\n"
            "print('ok')"
        ),
    },
    {
        "id": "b04",
        "title": "factorial",
        "objective": (
            PREAMBLE + "def factorial(n: int) -> int\n\n"
            "Return n! for a non-negative integer n: the product of every integer "
            "from 1 to n. factorial(0) is 1."
        ),
        "holdout_test": (
            "assert factorial(5) == 120\n"
            "assert factorial(0) == 1\n"
            "assert factorial(1) == 1\n"
            "assert factorial(6) == 720\n"
            "print('ok')"
        ),
    },
    {
        "id": "b05",
        "title": "is_palindrome",
        "objective": (
            PREAMBLE + "def is_palindrome(s: str) -> bool\n\n"
            "Return the bool True when s reads the same forwards and backwards, "
            "comparing case-insensitively. Do not strip spaces or punctuation: "
            "only letter case is ignored. The empty string is a palindrome."
        ),
        "holdout_test": (
            "assert is_palindrome('Racecar') is True\n"
            "assert is_palindrome('abc') is False\n"
            "assert is_palindrome('') is True\n"
            "assert is_palindrome('AbBa') is True\n"
            # Spaces are significant: stripping them would make this True.
            "assert is_palindrome('race car') is False\n"
            "print('ok')"
        ),
    },
    {
        "id": "b06",
        "title": "max_of_three",
        "objective": (
            PREAMBLE + "def max_of_three(a, b, c)\n\n"
            "Return the largest of the three values."
        ),
        "holdout_test": (
            "assert max_of_three(1, 9, 3) == 9\n"
            "assert max_of_three(-5, -2, -9) == -2\n"
            "assert max_of_three(4, 4, 4) == 4\n"
            "assert max_of_three(7, 2, 3) == 7\n"
            "print('ok')"
        ),
    },
    {
        "id": "b07",
        "title": "count_vowels",
        "objective": (
            PREAMBLE + "def count_vowels(s: str) -> int\n\n"
            "Return how many characters of s are vowels, counting a, e, i, o and u "
            "in either case. 'y' is not a vowel. An empty string has zero."
        ),
        "holdout_test": (
            "assert count_vowels('ether') == 2\n"
            "assert count_vowels('') == 0\n"
            "assert count_vowels('AEIOU') == 5\n"
            "assert count_vowels('rhythm') == 0\n"
            "assert count_vowels('Banana') == 3\n"
            "print('ok')"
        ),
    },
    {
        "id": "b08",
        "title": "flatten",
        "objective": (
            PREAMBLE + "def flatten(xss: list) -> list\n\n"
            "xss is a list of lists. Return one list holding the elements of every "
            "inner list, in order. Flatten a single level only. "
            "An empty outer list returns an empty list."
        ),
        "holdout_test": (
            "assert flatten([[1, 2], [3]]) == [1, 2, 3]\n"
            "assert flatten([]) == []\n"
            "assert flatten([[], [1]]) == [1]\n"
            "assert flatten([[1], [2], [3, 4]]) == [1, 2, 3, 4]\n"
            "print('ok')"
        ),
    },
    {
        "id": "b09",
        "title": "unique",
        "objective": (
            PREAMBLE + "def unique(xs: list) -> list\n\n"
            "Return the elements of xs with duplicates removed, keeping the first "
            "occurrence of each value and the original order."
        ),
        "holdout_test": (
            "assert unique([1, 2, 2, 3, 1]) == [1, 2, 3]\n"
            "assert unique([]) == []\n"
            "assert unique([5, 5, 5]) == [5]\n"
            "assert unique(['b', 'a', 'b']) == ['b', 'a']\n"
            "print('ok')"
        ),
    },
    {
        "id": "b10",
        "title": "word_count",
        "objective": (
            PREAMBLE + "def word_count(s: str) -> int\n\n"
            "Return the number of whitespace-separated words in s. A run of "
            "whitespace separates one word; an empty or blank string has zero."
        ),
        "holdout_test": (
            "assert word_count('one two three') == 3\n"
            "assert word_count('') == 0\n"
            "assert word_count('   ') == 0\n"
            "assert word_count('a  b') == 2\n"
            "assert word_count('solo') == 1\n"
            "print('ok')"
        ),
    },
    {
        "id": "b11",
        "title": "sum_list",
        "objective": (
            PREAMBLE + "def sum_list(xs: list)\n\n"
            "Return the sum of the numbers in xs. An empty list sums to 0."
        ),
        "holdout_test": (
            "assert sum_list([1, 2, 3, 4]) == 10\n"
            "assert sum_list([]) == 0\n"
            "assert sum_list([-1, 1]) == 0\n"
            "assert sum_list([2.5, 0.5]) == 3.0\n"
            "print('ok')"
        ),
    },
    {
        "id": "b12",
        "title": "clamp",
        "objective": (
            PREAMBLE + "def clamp(x, lo, hi)\n\n"
            "Return x limited to the inclusive range [lo, hi]: lo when x is below "
            "lo, hi when x is above hi, and x itself otherwise."
        ),
        "holdout_test": (
            "assert clamp(15, 0, 10) == 10\n"
            "assert clamp(-5, 0, 10) == 0\n"
            "assert clamp(5, 0, 10) == 5\n"
            "assert clamp(0, 0, 10) == 0\n"
            "assert clamp(10, 0, 10) == 10\n"
            "print('ok')"
        ),
    },
    {
        "id": "b13",
        "title": "title_case",
        "objective": (
            PREAMBLE + "def title_case(s: str) -> str\n\n"
            "Split s on whitespace, upper-case the first letter of each word and "
            "lower-case the rest of it, then join the words with single spaces. "
            "An empty string returns an empty string."
        ),
        "holdout_test": (
            "assert title_case('hello ether') == 'Hello Ether'\n"
            "assert title_case('') == ''\n"
            "assert title_case('HELLO') == 'Hello'\n"
            "assert title_case('a  b') == 'A B'\n"
            "print('ok')"
        ),
    },
    {
        "id": "b14",
        "title": "gcd",
        "objective": (
            PREAMBLE + "def gcd(a: int, b: int) -> int\n\n"
            "Return the greatest common divisor of a and b as a non-negative "
            "integer. gcd(n, 0) is n. Coprime inputs give 1."
        ),
        "holdout_test": (
            "assert gcd(48, 18) == 6\n"
            "assert gcd(7, 3) == 1\n"
            "assert gcd(5, 0) == 5\n"
            "assert gcd(0, 5) == 5\n"
            "assert gcd(12, 18) == 6\n"
            "print('ok')"
        ),
    },
    {
        "id": "b15",
        "title": "merge_sorted",
        "objective": (
            PREAMBLE + "def merge_sorted(a: list, b: list) -> list\n\n"
            "Both inputs are already sorted ascending. Return one sorted list "
            "holding every element of both, keeping duplicates. "
            "Either input may be empty."
        ),
        "holdout_test": (
            "assert merge_sorted([1, 3], [2, 4]) == [1, 2, 3, 4]\n"
            "assert merge_sorted([], [1]) == [1]\n"
            "assert merge_sorted([1, 2], []) == [1, 2]\n"
            "assert merge_sorted([], []) == []\n"
            "assert merge_sorted([1, 1], [1]) == [1, 1, 1]\n"
            "assert merge_sorted([1, 5], [2, 6]) == [1, 2, 5, 6]\n"
            "print('ok')"
        ),
    },
]


def load_tasks(fast: bool = False) -> List[Dict[str, str]]:
    """The tasks the bench actually serves.

    Tests must audit THIS, not the module literal: the equivalent curriculum
    test read tiers.json directly and stayed green while `load_tiers()` spliced
    leaking scratch tasks into the last tier at runtime.
    """
    tasks = [dict(t) for t in BENCH_TASKS]
    return tasks[:FAST_N] if fast else tasks


def audit_tasks(tasks: List[Dict[str, Any]]) -> List[str]:
    """Ways these tasks give away their own answer. Empty means safe to grade.

    Shared by scripts/quiz.py, scripts/hidden_quiz.py and
    scripts/dataset_quiz.py: one auditor, one grader (below), so a second
    weaker copy cannot drift into existence. hidden_quiz.py previously carried
    its own holdout runner with no leak check, no assertion floor and no
    sentinel, and it was the one feeding the scoreboard.
    """
    problems: List[str] = []
    for t in tasks:
        for p in check_task_leakage(t):
            problems.append(f"{t.get('id') or '?'}: {p}")
    return problems


# Older pipelines had no holdout parameter. Detect rather than assume, and
# grade locally when it is absent, so this never silently degrades to the exit
# code again.
_RUN_TAKES_HOLDOUT = "holdout_test" in inspect.signature(Pipeline.run).parameters


def run_task(pipe: Pipeline, objective: str, holdout_test: str) -> Any:
    """Generate for `objective`, never showing the model `holdout_test`."""
    if _RUN_TAKES_HOLDOUT:
        return pipe.run(objective, holdout_test=holdout_test)
    return pipe.run(objective)


def _holdout_detail(result: Any) -> str:
    for stage in reversed(list(getattr(result, "stages", None) or [])):
        if getattr(stage, "stage", "") == "holdout":
            return str(getattr(stage, "detail", ""))[:200]
    return ""


def grade_run(result: Any, holdout_test: str) -> Dict[str, Any]:
    """Holdout verdict for one generation. Fails closed.

    The single grading adapter for every harness in scripts/. All of the actual
    verification lives in core.holdout.grade_against_holdout.

    A task with no holdout is NOT a pass: nothing independent is left to grade
    it with, which is precisely the state this bench was in.
    """
    if not (holdout_test or "").strip():
        return {"ok": False, "detail": "task has no holdout_test — ungradeable"}

    verdict = getattr(result, "holdout_ok", None)
    if verdict is not None:
        # The pipeline already ran core.holdout for this task; grading again
        # would just burn a second sandbox on the same answer.
        return {
            "ok": bool(verdict),
            "detail": _holdout_detail(result) or ("passed" if verdict else "failed"),
        }

    graded = grade_against_holdout(getattr(result, "generated_code", "") or "", holdout_test)
    return {"ok": bool(graded.get("ok")), "detail": str(graded.get("reason") or "")[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="5-task smoke bench")
    args = ap.parse_args()
    tasks = load_tasks(fast=args.fast)

    # Enforced at the point of use, not only in tests. A bench that hands the
    # model its own answer produces a number that reads 1.000 and means
    # nothing — and that number ratchets the guardian baseline, so it is worse
    # than having no bench at all.
    leaks = audit_tasks(tasks)
    if leaks:
        print("REFUSING TO RUN — bench tasks leak their own answers:", file=sys.stderr)
        for problem in leaks:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    out_dir = ROOT / "memory" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    pipe = Pipeline()
    t0 = time.perf_counter()
    for i, task in enumerate(tasks, 1):
        obj = task["objective"]
        holdout = task.get("holdout_test") or ""
        print(
            f"[{i}/{len(tasks)}] {'FAST' if args.fast else 'FULL'} "
            f"{task['id']} {task['title']} ...",
            flush=True,
        )
        r = run_task(pipe, obj, holdout)
        graded = grade_run(r, holdout)
        results.append(
            {
                "i": i,
                "id": task["id"],
                "title": task["title"],
                "status": r.status,
                "confidence": r.confidence,
                "verification_score": r.verification_score,
                "exit_code": r.sandbox.exit_code if r.sandbox else None,
                "total_tests": r.sandbox.total_tests if r.sandbox else 0,
                "audit": bool(r.audit and r.audit.approved),
                # The pass criterion. Everything above it is diagnosis.
                "holdout_ok": graded["ok"],
                "holdout_detail": graded["detail"],
                "objective": obj[:80],
            }
        )
        print(
            f"  holdout_ok={graded['ok']} status={r.status} conf={r.confidence:.3f} "
            f"ver={r.verification_score:.3f} tests={results[-1]['total_tests']} "
            f"exit={results[-1]['exit_code']}"
            + (f" — {graded['detail']}" if not graded["ok"] and graded["detail"] else ""),
            flush=True,
        )
    ok = sum(1 for x in results if x["holdout_ok"] is True)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "fast" if args.fast else "full",
        "n": len(tasks),
        "pass": ok,
        "pass_rate": round(ok / max(1, len(tasks)), 3),
        # Recorded so a reader of memory/bench/*.json can tell a holdout-graded
        # run from a pre-fix "it exited 0" run.
        "graded_on": "holdout",
        "duration_s": round(time.perf_counter() - t0, 2),
        "results": results,
    }
    path = out_dir / f"bench_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    health = compute_health()
    guard = guardian_evaluate()
    write_scoreboard()
    print(
        json.dumps(
            {
                "mode": summary["mode"],
                "pass_rate": summary["pass_rate"],
                "pass": ok,
                "n": len(tasks),
                "graded_on": "holdout",
                "healthy": health.get("healthy"),
                "guardian_frozen": guard.get("frozen"),
            },
            indent=2,
        )
    )
    return 0 if ok == len(tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
