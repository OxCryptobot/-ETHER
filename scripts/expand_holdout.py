#!/usr/bin/env python3
"""Expand the held-out quiz toward 50 tasks (idempotent append).

This script used to append 30 tasks that looked like this, literally:

    Write only Python: def product(xs):
        r=1
        for x in xs: r*=x
        return r
    assert product([2,3,4])==24

The prompt contained the finished implementation AND the single assertion the
answer would be graded on. That is a transcription exercise, not an
evaluation: the model cannot fail it, so `pass_rate` measured copying speed and
then fed `core/health_metric.py`. `memory/quizzes/holdout_v1.json` was rewritten
to the v2 shape (signature + prose in `objective`, assertions in `holdout_test`
where the generator never sees them) — and running this script re-poisoned the
file it had just been cleaned of, at which point `scripts/quiz.py` refuses to
run at all (exit 2).

The 30 tasks below now follow the v2 contract:

  * `objective` gives a signature and describes the behaviour. No body, no
    assertions.
  * `holdout_test` carries 3-6 real assertions, deliberately covering cases the
    prose does not enumerate one by one — empty input, a single element,
    duplicates, negative numbers, identity/no-op arguments, aliasing of the
    caller's list. A holdout that only restates the example in the prompt
    cannot fail a plausible-but-wrong implementation, and a holdout that cannot
    fail grades nothing.

Nothing is written until the tasks pass three gates (fail closed — on any
problem the script exits non-zero and leaves both files untouched):

  1. `core.curriculum.check_task_leakage` on every task, including the ones
     already in the file, so this script can never append to (or extend) a
     poisoned dataset.
  2. Every holdout must contribute at least one assertion that
     `core.assert_audit.count_real_asserts` considers observable.
  3. Every task must be SOLVABLE and DISCRIMINATING: a reference
     implementation is graded through `core.holdout.grade_against_holdout`
     and must pass, and a deliberately wrong implementation is graded and must
     fail. The reference implementations live in `_SPECS` and are kept out of
     the JSON by construction (see EXTRA below) — they are the test of the
     test, never part of the prompt.

Gate 3 is not theoretical. The sibling dataset shipped `he04`, whose holdout
asserted `below_zero([1, 2, -3, 1, -2]) is False` while that balance ends at
-1: no correct implementation could ever have passed it, and the task silently
scored every model as wrong. Grading a known-good answer is how that was
caught, so it runs here before anything is written.

Usage:
    python scripts/expand_holdout.py              # verify, then append
    python scripts/expand_holdout.py --verify-only  # verify, write nothing
    python scripts/expand_holdout.py --skip-grading # gates 1+2 only (no sandbox)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.assert_audit import count_real_asserts
from core.curriculum import check_task_leakage

HOLDOUT = ROOT / "memory" / "quizzes" / "holdout_v1.json"
IDS = ROOT / "memory" / "quizzes" / "holdout_ids.json"


def _block(text: str) -> str:
    """Dedent a triple-quoted literal and trim the framing newlines."""
    return dedent(text).strip("\n")


# Each spec carries the prompt halves (signature + behaviour), the unseen
# assertions, and two implementations used only to validate the task itself.
_SPECS: List[Dict[str, str]] = [
    dict(
        id="h21",
        title="product",
        signature="def product(xs: list) -> int",
        behaviour=(
            "Return the product of every number in xs. An empty list has no "
            "factors, so it returns 1, the multiplicative identity."
        ),
        holdout=_block(
            """
            assert product([2, 3, 4]) == 24
            assert product([]) == 1
            assert product([7]) == 7
            assert product([2, 0, 5]) == 0
            assert product([-2, 3]) == -6
            print('ok')
            """
        ),
        reference=_block(
            """
            def product(xs):
                result = 1
                for x in xs:
                    result *= x
                return result
            """
        ),
        # Plausible: "an empty product is nothing", i.e. 0. Wrong identity.
        wrong=_block(
            """
            def product(xs):
                if not xs:
                    return 0
                result = 1
                for x in xs:
                    result *= x
                return result
            """
        ),
    ),
    dict(
        id="h22",
        title="drop_while",
        signature="def drop_while(xs: list, pred) -> list",
        behaviour=(
            "Discard elements from the front of xs for as long as pred(x) is "
            "truthy, and return a new list with everything from the first "
            "element that fails pred onward — including later elements that "
            "would satisfy pred. If pred holds for every element the result is "
            "empty."
        ),
        holdout=_block(
            """
            assert drop_while([0, 0, 1, 2], lambda x: x == 0) == [1, 2]
            assert drop_while([], lambda x: True) == []
            assert drop_while([1, 2, 3], lambda x: x > 10) == [1, 2, 3]
            assert drop_while([1, 0, 1], lambda x: x == 0) == [1, 0, 1]
            assert drop_while([0, 0], lambda x: x == 0) == []
            assert drop_while([0, 1, 0], lambda x: x == 0) == [1, 0]
            print('ok')
            """
        ),
        reference=_block(
            """
            def drop_while(xs, pred):
                i = 0
                while i < len(xs) and pred(xs[i]):
                    i += 1
                return list(xs[i:])
            """
        ),
        # Plausible: filter out everything matching pred, not just the prefix.
        wrong=_block(
            """
            def drop_while(xs, pred):
                return [x for x in xs if not pred(x)]
            """
        ),
    ),
    dict(
        id="h23",
        title="chunk",
        signature="def chunk(xs: list, n: int) -> list",
        behaviour=(
            "Split xs into consecutive lists of n elements, in order, and "
            "return the list of those chunks. When len(xs) is not a multiple "
            "of n the last chunk is shorter and is still included. An empty "
            "list produces an empty list."
        ),
        holdout=_block(
            """
            assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]
            assert chunk([1, 2, 3], 2) == [[1, 2], [3]]
            assert chunk([], 3) == []
            assert chunk([1, 2, 3], 1) == [[1], [2], [3]]
            assert chunk([1, 2], 5) == [[1, 2]]
            print('ok')
            """
        ),
        reference=_block(
            """
            def chunk(xs, n):
                return [list(xs[i:i + n]) for i in range(0, len(xs), n)]
            """
        ),
        # Plausible: only emit full-width chunks, silently dropping the tail.
        wrong=_block(
            """
            def chunk(xs, n):
                return [list(xs[i:i + n]) for i in range(0, len(xs) - n + 1, n)]
            """
        ),
    ),
    dict(
        id="h24",
        title="flatten_dict",
        signature="def flatten_dict(d: dict, prefix: str = '') -> dict",
        behaviour=(
            "Flatten a nested dict into a single level. A value that is itself "
            "a dict is flattened recursively, however deep it goes, and its "
            "keys are joined onto the outer key with a '.' separator; any "
            "other value is kept as it is. The optional prefix is prepended to "
            "every key produced, joined with the same separator. Assume all "
            "keys are strings."
        ),
        holdout=_block(
            """
            assert flatten_dict({'a': {'b': 1}}) == {'a.b': 1}
            assert flatten_dict({}) == {}
            assert flatten_dict({'a': 1, 'b': 2}) == {'a': 1, 'b': 2}
            assert flatten_dict({'a': {'b': {'c': 3}}}) == {'a.b.c': 3}
            assert flatten_dict({'a': {'b': 1}}, 'top') == {'top.a.b': 1}
            print('ok')
            """
        ),
        reference=_block(
            """
            def flatten_dict(d, prefix=''):
                out = {}
                for k, v in d.items():
                    key = prefix + '.' + k if prefix else k
                    if isinstance(v, dict):
                        out.update(flatten_dict(v, key))
                    else:
                        out[key] = v
                return out
            """
        ),
        # Plausible: joins one level of keys but never recurses further.
        wrong=_block(
            """
            def flatten_dict(d, prefix=''):
                out = {}
                for k, v in d.items():
                    key = prefix + '.' + k if prefix else k
                    if isinstance(v, dict):
                        for k2, v2 in v.items():
                            out[key + '.' + k2] = v2
                    else:
                        out[key] = v
                return out
            """
        ),
    ),
    dict(
        id="h25",
        title="levenshtein",
        signature="def levenshtein(a: str, b: str) -> int",
        behaviour=(
            "Return the Levenshtein edit distance between a and b: the "
            "smallest number of single-character insertions, deletions or "
            "substitutions that turns a into b. Identical strings are distance "
            "0, and comparing against an empty string costs one edit per "
            "character."
        ),
        holdout=_block(
            """
            assert levenshtein('kitten', 'sitting') == 3
            assert levenshtein('', '') == 0
            assert levenshtein('abc', 'abc') == 0
            assert levenshtein('', 'abc') == 3
            assert levenshtein('abc', '') == 3
            assert levenshtein('flaw', 'lawn') == 2
            print('ok')
            """
        ),
        reference=_block(
            """
            def levenshtein(a, b):
                dp = list(range(len(b) + 1))
                for i, ca in enumerate(a, 1):
                    prev = dp[:]
                    dp[0] = i
                    for j, cb in enumerate(b, 1):
                        dp[j] = min(prev[j] + 1, dp[j - 1] + 1, prev[j - 1] + (ca != cb))
                return dp[-1]
            """
        ),
        # Plausible: Hamming distance plus the length difference. Agrees on
        # 'kitten'/'sitting' and disagrees wherever a shift is cheaper.
        wrong=_block(
            """
            def levenshtein(a, b):
                diff = sum(1 for ca, cb in zip(a, b) if ca != cb)
                return diff + abs(len(a) - len(b))
            """
        ),
    ),
    dict(
        id="h26",
        title="powerset_size",
        signature="def powerset_size(n: int) -> int",
        behaviour=(
            "Return how many distinct subsets a set of n elements has, for any "
            "n >= 0. The empty set still has exactly one subset: itself."
        ),
        holdout=_block(
            """
            assert powerset_size(0) == 1
            assert powerset_size(1) == 2
            assert powerset_size(3) == 8
            assert powerset_size(10) == 1024
            print('ok')
            """
        ),
        reference=_block(
            """
            def powerset_size(n):
                return 2 ** n
            """
        ),
        # Plausible: counts PROPER subsets, missing the set itself.
        wrong=_block(
            """
            def powerset_size(n):
                return 2 ** n - 1
            """
        ),
    ),
    dict(
        id="h27",
        title="rle_decode",
        signature="def rle_decode(pairs: list) -> str",
        behaviour=(
            "pairs is a list of (character, count) tuples. Return the string "
            "that repeats each character count times, concatenated in the "
            "given order. Counts are never negative, and a count of 0 "
            "contributes nothing. An empty list decodes to an empty string."
        ),
        holdout=_block(
            """
            assert rle_decode([('a', 2), ('b', 1)]) == 'aab'
            assert rle_decode([]) == ''
            assert rle_decode([('x', 0), ('y', 3)]) == 'yyy'
            assert rle_decode([('z', 1)]) == 'z'
            assert rle_decode([('a', 2), ('a', 2)]) == 'aaaa'
            print('ok')
            """
        ),
        reference=_block(
            """
            def rle_decode(pairs):
                return ''.join(ch * n for ch, n in pairs)
            """
        ),
        # Plausible: forgets the count entirely.
        wrong=_block(
            """
            def rle_decode(pairs):
                return ''.join(ch for ch, n in pairs)
            """
        ),
    ),
    dict(
        id="h28",
        title="sliding_max",
        signature="def sliding_max(xs: list, k: int) -> list",
        behaviour=(
            "Return the maximum of every contiguous window of length k in xs, "
            "left to right. There are len(xs) - k + 1 such windows, so when k "
            "is larger than the list there are none and the result is empty."
        ),
        holdout=_block(
            """
            assert sliding_max([1, 3, 2, 5], 2) == [3, 3, 5]
            assert sliding_max([1, 2, 3], 1) == [1, 2, 3]
            assert sliding_max([4, 1, 2], 3) == [4]
            assert sliding_max([1, 2], 5) == []
            assert sliding_max([], 2) == []
            assert sliding_max([-5, -2, -9], 2) == [-2, -2]
            print('ok')
            """
        ),
        reference=_block(
            """
            def sliding_max(xs, k):
                return [max(xs[i:i + k]) for i in range(len(xs) - k + 1)]
            """
        ),
        # Plausible off-by-one: drops the final window.
        wrong=_block(
            """
            def sliding_max(xs, k):
                return [max(xs[i:i + k]) for i in range(len(xs) - k)]
            """
        ),
    ),
    dict(
        id="h29",
        title="invert_map",
        signature="def invert_map(d: dict) -> dict",
        behaviour=(
            "Return a new dict mapping each value of d back to its key. When "
            "several keys share a value the LAST one in iteration order wins. "
            "An empty dict inverts to an empty dict, and d itself must not be "
            "modified."
        ),
        holdout=_block(
            """
            assert invert_map({'a': 1}) == {1: 'a'}
            assert invert_map({}) == {}
            assert invert_map({'a': 1, 'b': 2}) == {1: 'a', 2: 'b'}
            assert invert_map({'a': 1, 'b': 1}) == {1: 'b'}
            src = {'a': 1}
            out = invert_map(src)
            out[2] = 'z'
            assert src == {'a': 1}
            print('ok')
            """
        ),
        reference=_block(
            """
            def invert_map(d):
                return {v: k for k, v in d.items()}
            """
        ),
        # Plausible: first key wins on a collision.
        wrong=_block(
            """
            def invert_map(d):
                out = {}
                for k, v in d.items():
                    if v not in out:
                        out[v] = k
                return out
            """
        ),
    ),
    dict(
        id="h30",
        title="take",
        signature="def take(xs: list, n: int) -> list",
        behaviour=(
            "Return a new list holding the first n elements of xs, in order. "
            "When n is 0 or negative the result is empty; when n exceeds the "
            "length of xs the result is a copy of the whole list. xs is never "
            "modified and the result is always a fresh list."
        ),
        holdout=_block(
            """
            assert take([1, 2, 3], 2) == [1, 2]
            assert take([1, 2, 3], 0) == []
            assert take([1, 2, 3], -1) == []
            assert take([1, 2], 5) == [1, 2]
            assert take([], 3) == []
            xs = [1, 2, 3]
            out = take(xs, 3)
            out.append(4)
            assert xs == [1, 2, 3]
            print('ok')
            """
        ),
        reference=_block(
            """
            def take(xs, n):
                if n <= 0:
                    return []
                return list(xs[:n])
            """
        ),
        # Plausible: the obvious slice, which reads a negative n from the END.
        wrong=_block(
            """
            def take(xs, n):
                return list(xs[:n])
            """
        ),
    ),
    dict(
        id="h31",
        title="zip_to_dict",
        signature="def zip_to_dict(keys: list, vals: list) -> dict",
        behaviour=(
            "Pair each key with the value at the same position and return the "
            "resulting dict. Stop at the end of the shorter input, ignoring "
            "any leftovers. If a key appears more than once, the value from "
            "its LAST position wins."
        ),
        holdout=_block(
            """
            assert zip_to_dict(['a', 'b'], [1, 2]) == {'a': 1, 'b': 2}
            assert zip_to_dict([], []) == {}
            assert zip_to_dict(['a', 'b'], [1]) == {'a': 1}
            assert zip_to_dict(['a'], [1, 2, 3]) == {'a': 1}
            assert zip_to_dict(['a', 'a'], [1, 2]) == {'a': 2}
            print('ok')
            """
        ),
        reference=_block(
            """
            def zip_to_dict(keys, vals):
                return dict(zip(keys, vals))
            """
        ),
        # Plausible: keeps the first binding for a repeated key.
        wrong=_block(
            """
            def zip_to_dict(keys, vals):
                out = {}
                for k, v in zip(keys, vals):
                    out.setdefault(k, v)
                return out
            """
        ),
    ),
    dict(
        id="h32",
        title="is_sorted",
        signature="def is_sorted(xs: list) -> bool",
        behaviour=(
            "Return the bool True when xs is in non-decreasing order, i.e. no "
            "element is smaller than the one before it. Equal neighbours are "
            "allowed. A list of fewer than two elements is sorted."
        ),
        holdout=_block(
            """
            assert is_sorted([1, 2, 2, 3]) is True
            assert is_sorted([2, 1]) is False
            assert is_sorted([]) is True
            assert is_sorted([5]) is True
            assert is_sorted([1, 3, 2, 4]) is False
            print('ok')
            """
        ),
        reference=_block(
            """
            def is_sorted(xs):
                return all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1))
            """
        ),
        # Plausible: requires STRICTLY increasing, so ties read as unsorted.
        wrong=_block(
            """
            def is_sorted(xs):
                return all(xs[i] < xs[i + 1] for i in range(len(xs) - 1))
            """
        ),
    ),
    dict(
        id="h33",
        title="mean",
        signature="def mean(xs: list)",
        behaviour=(
            "Return the arithmetic mean of the numbers in xs, keeping any "
            "fractional part. An empty list has no mean, so return None rather "
            "than a number."
        ),
        holdout=_block(
            """
            assert mean([2, 4]) == 3
            assert mean([]) is None
            assert mean([5]) == 5
            assert mean([1, 2]) == 1.5
            assert mean([-2, 2]) == 0
            print('ok')
            """
        ),
        reference=_block(
            """
            def mean(xs):
                if not xs:
                    return None
                return sum(xs) / len(xs)
            """
        ),
        # Plausible: the empty case answered with 0, which is a real value.
        wrong=_block(
            """
            def mean(xs):
                if not xs:
                    return 0
                return sum(xs) / len(xs)
            """
        ),
    ),
    dict(
        id="h34",
        title="clamp_list",
        signature="def clamp_list(xs: list, lo, hi) -> list",
        behaviour=(
            "Return a new list in which every element of xs is pulled into the "
            "inclusive range lo..hi: anything below lo becomes lo, anything "
            "above hi becomes hi, and everything else is unchanged."
        ),
        holdout=_block(
            """
            assert clamp_list([0, 5, 10], 1, 8) == [1, 5, 8]
            assert clamp_list([], 0, 1) == []
            assert clamp_list([2, 3], 0, 10) == [2, 3]
            assert clamp_list([-5, -1], -3, 3) == [-3, -1]
            assert clamp_list([7], 2, 2) == [2]
            print('ok')
            """
        ),
        reference=_block(
            """
            def clamp_list(xs, lo, hi):
                return [max(lo, min(hi, x)) for x in xs]
            """
        ),
        # Plausible: clamps the lower bound only.
        wrong=_block(
            """
            def clamp_list(xs, lo, hi):
                return [max(lo, x) for x in xs]
            """
        ),
    ),
    dict(
        id="h35",
        title="count_if",
        signature="def count_if(xs: list, pred) -> int",
        behaviour=(
            "Return how many elements of xs satisfy the predicate, counting "
            "every x for which pred(x) is TRUTHY — not only those where it is "
            "literally True. An empty list counts 0."
        ),
        holdout=_block(
            """
            assert count_if([1, 2, 3, 4], lambda x: x % 2 == 0) == 2
            assert count_if([], lambda x: True) == 0
            assert count_if([1, 3], lambda x: x % 2 == 0) == 0
            assert count_if([2, 4], lambda x: x % 2 == 0) == 2
            assert count_if([0, 1, 2], lambda x: x) == 2
            assert count_if(['', 'a'], lambda s: s) == 1
            print('ok')
            """
        ),
        reference=_block(
            """
            def count_if(xs, pred):
                return sum(1 for x in xs if pred(x))
            """
        ),
        # Plausible: identity comparison against True, which rejects truthy
        # non-bool results.
        wrong=_block(
            """
            def count_if(xs, pred):
                return sum(1 for x in xs if pred(x) is True)
            """
        ),
    ),
    dict(
        id="h36",
        title="repeat",
        signature="def repeat(x, n: int) -> list",
        behaviour=(
            "Return a list containing the value x repeated n times. When n is "
            "0 or negative the list is empty."
        ),
        holdout=_block(
            """
            assert repeat('z', 3) == ['z', 'z', 'z']
            assert repeat('z', 0) == []
            assert repeat(1, -2) == []
            assert repeat(None, 1) == [None]
            assert len(repeat(0, 4)) == 4
            print('ok')
            """
        ),
        reference=_block(
            """
            def repeat(x, n):
                if n <= 0:
                    return []
                return [x] * n
            """
        ),
        # Plausible: assumes at least one copy is always wanted.
        wrong=_block(
            """
            def repeat(x, n):
                return [x] * max(1, n)
            """
        ),
    ),
    dict(
        id="h37",
        title="head_tail",
        signature="def head_tail(xs: list) -> tuple",
        behaviour=(
            "Return the tuple (head, tail): head is the first element of xs "
            "and tail is a NEW list with the remaining elements in order. An "
            "empty list gives (None, []). The caller's list is never modified "
            "and never aliased by the tail."
        ),
        holdout=_block(
            """
            assert head_tail([1, 2, 3]) == (1, [2, 3])
            assert head_tail([]) == (None, [])
            assert head_tail([9]) == (9, [])
            assert head_tail(['a', 'b'])[0] == 'a'
            xs = [1, 2]
            head, tail = head_tail(xs)
            tail.append(99)
            assert xs == [1, 2]
            print('ok')
            """
        ),
        reference=_block(
            """
            def head_tail(xs):
                if not xs:
                    return (None, [])
                return (xs[0], list(xs[1:]))
            """
        ),
        # Plausible: hands back the original list as the "tail".
        wrong=_block(
            """
            def head_tail(xs):
                if not xs:
                    return (None, [])
                return (xs[0], xs)
            """
        ),
    ),
    dict(
        id="h38",
        title="merge_unique",
        signature="def merge_unique(a: list, b: list) -> list",
        behaviour=(
            "Return the elements of a followed by the elements of b with "
            "duplicates removed: keep only the first occurrence of each value "
            "and preserve that first-seen order. Repeats within a single input "
            "count as duplicates too."
        ),
        holdout=_block(
            """
            assert merge_unique([1, 2], [2, 3]) == [1, 2, 3]
            assert merge_unique([], []) == []
            assert merge_unique([1, 1], [1]) == [1]
            assert merge_unique([], [3, 1]) == [3, 1]
            assert merge_unique([2, 1], [1, 2]) == [2, 1]
            print('ok')
            """
        ),
        reference=_block(
            """
            def merge_unique(a, b):
                seen = set()
                out = []
                for x in list(a) + list(b):
                    if x not in seen:
                        seen.add(x)
                        out.append(x)
                return out
            """
        ),
        # Plausible: set union, which silently sorts and loses input order.
        wrong=_block(
            """
            def merge_unique(a, b):
                return sorted(set(a) | set(b))
            """
        ),
    ),
    dict(
        id="h39",
        title="index_map",
        signature="def index_map(xs: list) -> dict",
        behaviour=(
            "Return a dict mapping each element of xs to its position in the "
            "list. If a value appears more than once, the LAST position wins. "
            "An empty list gives an empty dict."
        ),
        holdout=_block(
            """
            assert index_map(['a', 'b']) == {'a': 0, 'b': 1}
            assert index_map([]) == {}
            assert index_map(['a', 'b', 'a']) == {'a': 2, 'b': 1}
            assert index_map(['x']) == {'x': 0}
            print('ok')
            """
        ),
        reference=_block(
            """
            def index_map(xs):
                return {x: i for i, x in enumerate(xs)}
            """
        ),
        # Plausible: records the first sighting instead of the last.
        wrong=_block(
            """
            def index_map(xs):
                out = {}
                for i, x in enumerate(xs):
                    if x not in out:
                        out[x] = i
                return out
            """
        ),
    ),
    dict(
        id="h40",
        title="safe_div",
        signature="def safe_div(a, b)",
        behaviour=(
            "Return a divided by b as a true division that keeps the "
            "fractional part. Dividing by 0 has no result, so return None "
            "instead of raising."
        ),
        holdout=_block(
            """
            assert safe_div(6, 3) == 2
            assert safe_div(1, 0) is None
            assert safe_div(7, 2) == 3.5
            assert safe_div(0, 5) == 0
            assert safe_div(-6, 3) == -2
            print('ok')
            """
        ),
        reference=_block(
            """
            def safe_div(a, b):
                if b == 0:
                    return None
                return a / b
            """
        ),
        # Plausible: floor division, which truncates 7/2 to 3.
        wrong=_block(
            """
            def safe_div(a, b):
                if b == 0:
                    return None
                return a // b
            """
        ),
    ),
    dict(
        id="h41",
        title="digits_sum",
        signature="def digits_sum(n: int) -> int",
        behaviour=(
            "Return the sum of the decimal digits of the integer n. A minus "
            "sign is not a digit, so a negative number uses the digits of its "
            "absolute value. The digits of 0 sum to 0."
        ),
        holdout=_block(
            """
            assert digits_sum(123) == 6
            assert digits_sum(-45) == 9
            assert digits_sum(0) == 0
            assert digits_sum(9) == 9
            assert digits_sum(1000000) == 1
            print('ok')
            """
        ),
        reference=_block(
            """
            def digits_sum(n):
                return sum(int(c) for c in str(abs(n)))
            """
        ),
        # Plausible: forgets the sign character and blows up on negatives.
        wrong=_block(
            """
            def digits_sum(n):
                return sum(int(c) for c in str(n))
            """
        ),
    ),
    dict(
        id="h42",
        title="dedupe_adjacent",
        signature="def dedupe_adjacent(xs: list) -> list",
        behaviour=(
            "Return a new list in which every run of CONSECUTIVE equal "
            "elements in xs is collapsed to a single element. A value that "
            "repeats later on, without touching its earlier occurrence, is "
            "kept every time."
        ),
        holdout=_block(
            """
            assert dedupe_adjacent([1, 1, 2, 2, 2, 3]) == [1, 2, 3]
            assert dedupe_adjacent([]) == []
            assert dedupe_adjacent([1, 2, 1]) == [1, 2, 1]
            assert dedupe_adjacent([4, 4, 4]) == [4]
            assert dedupe_adjacent([1]) == [1]
            print('ok')
            """
        ),
        reference=_block(
            """
            def dedupe_adjacent(xs):
                out = []
                for x in xs:
                    if not out or x != out[-1]:
                        out.append(x)
                return out
            """
        ),
        # Plausible: global de-duplication, which also eats non-adjacent
        # repeats.
        wrong=_block(
            """
            def dedupe_adjacent(xs):
                seen = set()
                out = []
                for x in xs:
                    if x not in seen:
                        seen.add(x)
                        out.append(x)
                return out
            """
        ),
    ),
    dict(
        id="h43",
        title="rotate_right",
        signature="def rotate_right(xs: list, k: int) -> list",
        behaviour=(
            "Return a new list with the elements of xs rotated k places to the "
            "RIGHT, so the last k elements move to the front keeping their "
            "order. k may be 0, and it may be larger than the list. Rotating "
            "an empty list gives an empty list."
        ),
        holdout=_block(
            """
            assert rotate_right([1, 2, 3, 4], 1) == [4, 1, 2, 3]
            assert rotate_right([1, 2, 3, 4], 0) == [1, 2, 3, 4]
            assert rotate_right([1, 2, 3, 4], 4) == [1, 2, 3, 4]
            assert rotate_right([1, 2, 3], 5) == [2, 3, 1]
            assert rotate_right([], 2) == []
            print('ok')
            """
        ),
        reference=_block(
            """
            def rotate_right(xs, k):
                if not xs:
                    return []
                k = k % len(xs)
                return list(xs[len(xs) - k:]) + list(xs[:len(xs) - k])
            """
        ),
        # Plausible: rotates the wrong way.
        wrong=_block(
            """
            def rotate_right(xs, k):
                if not xs:
                    return []
                k = k % len(xs)
                return list(xs[k:]) + list(xs[:k])
            """
        ),
    ),
    dict(
        id="h44",
        title="is_palindrome",
        signature="def is_palindrome(s: str) -> bool",
        behaviour=(
            "Return the bool True when s reads the same forwards and backwards "
            "once every character that is not a letter or a digit is ignored "
            "and letter case is disregarded. The empty string is a palindrome."
        ),
        holdout=_block(
            """
            assert is_palindrome('A man, a plan, a canal: Panama') is True
            assert is_palindrome('hello') is False
            assert is_palindrome('') is True
            assert is_palindrome('Aa') is True
            assert is_palindrome('ab12ba') is False
            assert is_palindrome('12321') is True
            print('ok')
            """
        ),
        reference=_block(
            """
            def is_palindrome(s):
                t = ''.join(c.lower() for c in s if c.isalnum())
                return t == t[::-1]
            """
        ),
        # Plausible: strips spaces and case but keeps punctuation.
        wrong=_block(
            """
            def is_palindrome(s):
                t = s.lower().replace(' ', '')
                return t == t[::-1]
            """
        ),
    ),
    dict(
        id="h45",
        title="gcd",
        signature="def gcd(a: int, b: int) -> int",
        behaviour=(
            "Return the greatest common divisor of the integers a and b as a "
            "NON-NEGATIVE number. The gcd of 0 and n is n, the gcd of 0 and 0 "
            "is 0, and negative inputs give the same answer as their absolute "
            "values."
        ),
        holdout=_block(
            """
            assert gcd(12, 18) == 6
            assert gcd(7, 3) == 1
            assert gcd(0, 5) == 5
            assert gcd(5, 0) == 5
            assert gcd(0, 0) == 0
            assert gcd(-12, 18) == 6
            assert gcd(12, -18) == 6
            print('ok')
            """
        ),
        reference=_block(
            """
            def gcd(a, b):
                a, b = abs(a), abs(b)
                while b:
                    a, b = b, a % b
                return a
            """
        ),
        # Plausible: Euclid without normalising the sign, which returns a
        # negative divisor for a negative second argument.
        wrong=_block(
            """
            def gcd(a, b):
                while b:
                    a, b = b, a % b
                return a
            """
        ),
    ),
    dict(
        id="h46",
        title="flatten_once",
        signature="def flatten_once(xs: list) -> list",
        behaviour=(
            "Return a new list with exactly ONE level of nesting removed: each "
            "element that is a list is replaced by its own elements, in order, "
            "and every other element is kept as it is. Anything nested more "
            "deeply than one level stays nested."
        ),
        holdout=_block(
            """
            assert flatten_once([1, [2, 3], 4]) == [1, 2, 3, 4]
            assert flatten_once([]) == []
            assert flatten_once([[], [1]]) == [1]
            assert flatten_once([1, [2, [3]]]) == [1, 2, [3]]
            assert flatten_once([[1], [2]]) == [1, 2]
            print('ok')
            """
        ),
        reference=_block(
            """
            def flatten_once(xs):
                out = []
                for x in xs:
                    if isinstance(x, list):
                        out.extend(x)
                    else:
                        out.append(x)
                return out
            """
        ),
        # Plausible: flattens all the way down.
        wrong=_block(
            """
            def flatten_once(xs):
                out = []
                for x in xs:
                    if isinstance(x, list):
                        out.extend(flatten_once(x))
                    else:
                        out.append(x)
                return out
            """
        ),
    ),
    dict(
        id="h47",
        title="mode",
        signature="def mode(xs: list)",
        behaviour=(
            "Return the value that occurs most often in xs. When several "
            "values tie for most frequent, return the one whose first "
            "occurrence comes earliest. An empty list has no mode, so return "
            "None."
        ),
        holdout=_block(
            """
            assert mode([1, 2, 2, 3]) == 2
            assert mode([]) is None
            assert mode([7]) == 7
            assert mode([1, 1, 2, 2]) == 1
            assert mode(['b', 'a', 'a']) == 'a'
            print('ok')
            """
        ),
        reference=_block(
            """
            def mode(xs):
                from collections import Counter
                if not xs:
                    return None
                return Counter(xs).most_common(1)[0][0]
            """
        ),
        # Plausible: reads the wrong end of most_common().
        wrong=_block(
            """
            def mode(xs):
                from collections import Counter
                if not xs:
                    return None
                return Counter(xs).most_common()[-1][0]
            """
        ),
    ),
    dict(
        id="h48",
        title="binary_search",
        signature="def binary_search(xs: list, target) -> int",
        behaviour=(
            "xs is sorted in ascending order. Return the index at which target "
            "appears, or -1 when it is absent. Halve the search range each "
            "step rather than scanning. An empty list always answers -1, and "
            "the first and last elements are findable like any other."
        ),
        holdout=_block(
            """
            assert binary_search([1, 3, 5, 7], 5) == 2
            assert binary_search([1, 3, 5, 7], 2) == -1
            assert binary_search([], 1) == -1
            assert binary_search([4], 4) == 0
            assert binary_search([1, 3, 5, 7], 1) == 0
            assert binary_search([1, 3, 5, 7], 7) == 3
            print('ok')
            """
        ),
        reference=_block(
            """
            def binary_search(xs, target):
                lo, hi = 0, len(xs) - 1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    if xs[mid] == target:
                        return mid
                    if xs[mid] < target:
                        lo = mid + 1
                    else:
                        hi = mid - 1
                return -1
            """
        ),
        # Plausible off-by-one: the last element is never examined.
        wrong=_block(
            """
            def binary_search(xs, target):
                lo, hi = 0, len(xs) - 2
                while lo <= hi:
                    mid = (lo + hi) // 2
                    if xs[mid] == target:
                        return mid
                    if xs[mid] < target:
                        lo = mid + 1
                    else:
                        hi = mid - 1
                return -1
            """
        ),
    ),
    dict(
        id="h49",
        title="column_max",
        signature="def column_max(m: list) -> list",
        behaviour=(
            "m is a rectangular matrix given as a list of equal-length row "
            "lists. Return a list holding the largest value of each COLUMN, in "
            "column order, so the result is as long as one row. An empty "
            "matrix gives an empty list."
        ),
        holdout=_block(
            """
            assert column_max([[1, 2], [3, 4]]) == [3, 4]
            assert column_max([]) == []
            assert column_max([[5, 1, 9]]) == [5, 1, 9]
            assert column_max([[1], [2], [3]]) == [3]
            assert column_max([[-5, -2], [-9, -1]]) == [-5, -1]
            print('ok')
            """
        ),
        reference=_block(
            """
            def column_max(m):
                if not m:
                    return []
                return [max(row[j] for row in m) for j in range(len(m[0]))]
            """
        ),
        # Plausible: reduces along rows instead of columns.
        wrong=_block(
            """
            def column_max(m):
                return [max(row) for row in m]
            """
        ),
    ),
    dict(
        id="h50",
        title="running_max",
        signature="def running_max(xs: list) -> list",
        behaviour=(
            "Return a list of the same length whose ith element is the largest "
            "value among xs[0] through xs[i] inclusive, so the result never "
            "decreases. An empty list gives an empty list."
        ),
        holdout=_block(
            """
            assert running_max([1, 3, 2, 5]) == [1, 3, 3, 5]
            assert running_max([]) == []
            assert running_max([4]) == [4]
            assert running_max([3, 2, 1]) == [3, 3, 3]
            assert running_max([-5, -9, -1]) == [-5, -5, -1]
            print('ok')
            """
        ),
        reference=_block(
            """
            def running_max(xs):
                out = []
                best = None
                for x in xs:
                    best = x if best is None or x > best else best
                    out.append(best)
                return out
            """
        ),
        # Plausible: the running maximum confused with the global maximum.
        wrong=_block(
            """
            def running_max(xs):
                if not xs:
                    return []
                return [max(xs)] * len(xs)
            """
        ),
    ),
]


def _objective(spec: Dict[str, str]) -> str:
    """Prompt text: instruction, signature, behaviour. No body, no asserts."""
    return (
        "Write only Python, no markdown.\n\n"
        f"Implement:\n\n{spec['signature']}\n\n{spec['behaviour']}"
    )


# The tasks that get written. Built field by field so an implementation cannot
# reach the dataset even by accident: `reference` and `wrong` are addressed
# through separate maps and are never copied into a task dict.
EXTRA: List[Dict[str, str]] = [
    {
        "id": spec["id"],
        "title": spec["title"],
        "objective": _objective(spec),
        "holdout_test": spec["holdout"],
    }
    for spec in _SPECS
]

REFERENCE: Dict[str, str] = {spec["id"]: spec["reference"] for spec in _SPECS}
WRONG: Dict[str, str] = {spec["id"]: spec["wrong"] for spec in _SPECS}


def audit_tasks(tasks: List[Dict[str, Any]]) -> List[str]:
    """Static problems with `tasks`: leakage, empty holdouts, duplicate ids."""
    problems: List[str] = []
    seen: set[str] = set()
    for task in tasks:
        task_id = str(task.get("id") or "?")
        if task_id in seen:
            problems.append(f"[{task_id}] duplicate id")
        seen.add(task_id)
        for problem in check_task_leakage(task):
            problems.append(f"[{task_id}] {problem}")
        n = count_real_asserts(str(task.get("holdout_test") or ""))
        if n < 1:
            problems.append(f"[{task_id}] holdout has no observable assertions")
    return problems


def verify_solvable(tasks: List[Dict[str, Any]], timeout: int = 60) -> List[str]:
    """Grade each task's reference and wrong implementation in the sandbox.

    A holdout is only worth running if a correct answer can pass it (otherwise
    it scores everyone as wrong, the `he04` defect) AND a wrong answer fails it
    (otherwise it certifies everyone). Both directions are checked here, for
    every task, before anything is written.
    """
    from core.holdout import grade_against_holdout

    problems: List[str] = []
    for task in tasks:
        task_id = str(task.get("id") or "?")
        holdout = str(task.get("holdout_test") or "")
        reference = REFERENCE.get(task_id)
        wrong = WRONG.get(task_id)
        if not reference or not wrong:
            problems.append(f"[{task_id}] no reference/wrong implementation to verify with")
            continue

        good = grade_against_holdout(reference, holdout, timeout=timeout)
        if not good.get("ok"):
            problems.append(
                f"[{task_id}] UNSOLVABLE — a correct implementation fails the holdout "
                f"({good.get('reason')}; {(good.get('stderr') or '').strip()[-160:]})"
            )

        bad = grade_against_holdout(wrong, holdout, timeout=timeout)
        if bad.get("ok"):
            problems.append(
                f"[{task_id}] NOT DISCRIMINATING — a wrong implementation passes the holdout"
            )
    return problems


def load_existing(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"tasks": []}
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--verify-only",
        action="store_true",
        help="run every check and write nothing",
    )
    ap.add_argument(
        "--skip-grading",
        action="store_true",
        help="skip the sandbox solvability check (leakage checks still run)",
    )
    args = ap.parse_args(argv)

    data = load_existing(HOLDOUT)
    tasks = list(data.get("tasks") or [])
    have = {t.get("id") for t in tasks}
    merged = tasks + [t for t in EXTRA if t["id"] not in have]

    # Gate 1+2: nothing leaks, every holdout can actually fail. Applied to the
    # MERGED set, so this script can neither add a poisoned task nor extend an
    # already-poisoned file.
    problems = audit_tasks(merged)
    if problems:
        print("REFUSING TO WRITE — task audit failed:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    # Gate 3: every task we own is solvable and discriminates.
    if not args.skip_grading:
        problems = verify_solvable(EXTRA)
        if problems:
            print("REFUSING TO WRITE — holdout verification failed:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 3

    if args.verify_only:
        print(json.dumps({"verified": len(EXTRA), "would_write": len(merged)}, indent=2))
        return 0

    data["tasks"] = merged
    data.setdefault("version", 2)
    HOLDOUT.parent.mkdir(parents=True, exist_ok=True)
    HOLDOUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    ids = sorted(str(t.get("id")) for t in merged if t.get("id"))
    IDS.write_text(json.dumps({"ids": ids}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": len(merged), "ids": len(ids), "graded": not args.skip_grading}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
