#!/usr/bin/env python3
"""Build `memory/quizzes/headroom_v1.json` — a bench with room to be wrong.

WHY THIS EXISTS
---------------
The regression bench in `scripts/bench.py` asks for `is_even`, `add` and
`reverse_string`. A bare 35B answers all fifteen. That is a fine smoke test and
a useless experiment: if the ceiling is 1.0 and the floor is 1.0, the interval
in which a scaffold could demonstrate value is narrower than the sampling noise
of a single run, so an ablation over that suite returns "no difference" whether
or not @ETHER does anything at all. A null result that is guaranteed in advance
is not evidence.

This suite is built for the opposite property: forty tasks chosen so a
competent bare model lands somewhere around 0.4-0.7. Difficulty here is not
trickiness — no obscure trivia, no third-party libraries, no puzzles. It is
the ordinary difficulty of production code: several constraints that interact,
stateful objects with invariants, exact output formats, specific exception
types, functions forbidden from mutating their arguments, and a few problems
where the obvious greedy answer is wrong.

WHAT IS ACTUALLY VERIFIED BEFORE ANYTHING IS WRITTEN
----------------------------------------------------
A benchmark that does not discriminate is worse than no benchmark, because it
still produces a number. Five gates run first, and any failure exits non-zero
having written nothing:

  1. `core.curriculum.check_task_leakage` — no implementation and no holdout
     assertion may appear in the objective the generator is shown.
  2. `core.prompt_guard.check(objective, holdout_test)` — the same check from
     the other side, on the finished prompt.
  3. SOLVABLE — a reference implementation is graded through
     `core.holdout.grade_against_holdout` and must pass. This is not
     theoretical: the sibling dataset once shipped `below_zero([1,2,-3,1,-2])
     is False` for a balance that ends at -1, an assertion no correct program
     could satisfy, and it silently scored every model as wrong.
  4. DISCRIMINATING — mutation scoring. For each task, >= 15 single-edit
     mutants of the reference are generated (swap +/-, < to <=, and/or,
     off-by-one on literals and indices, drop a branch, drop a `not`, return a
     constant, return the argument unchanged) and graded. `killed / total`
     must be >= 0.90. A holdout that cannot kill a mutant cannot fail a
     plausible-but-wrong answer either, which is the failure mode that made
     the old bench read 1.000.
  5. No duplicate entry-point names, and none colliding with `scripts/bench.py`,
     `memory/quizzes/holdout_v1.json` or `memory/quizzes/hidden_humaneval.json`
     — a task the model has already been graded on elsewhere is a leak.

THE REFERENCE NEVER SHIPS
-------------------------
`reference` exists only to test the test. It is the answer, so writing it into
the dataset would put the answer one BM25 hit away from the prompt (exactly how
`bench.py` leaked twelve of fifteen assertions once). Task dicts are assembled
field by field in `public_task()` — never by copying the spec and deleting a
key, which is the version of this that silently regresses — and
`tests/test_headroom_suite.py` pins it.

Usage:
    python scripts/build_headroom.py                # verify all gates, write
    python scripts/build_headroom.py --verify-only  # verify, write nothing
    python scripts/build_headroom.py --static-only  # gates 1,2,5 (no sandbox)
    python scripts/build_headroom.py --jobs 8       # parallel grading

Grading costs ~0.3s per call and the suite is ~40 tasks x ~21 grades, so a full
run is a few minutes. No LLM is ever invoked: `grade_against_holdout` runs the
sandbox, not the model.
"""

from __future__ import annotations

import argparse
import ast
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.assert_audit import count_real_asserts  # noqa: E402
from core.curriculum import check_task_leakage  # noqa: E402
from core.prompt_guard import assertion_lines, check as prompt_check  # noqa: E402

OUT_PATH = ROOT / "memory" / "quizzes" / "headroom_v1.json"
BENCH_PATH = ROOT / "scripts" / "bench.py"
HOLDOUT_PATH = ROOT / "memory" / "quizzes" / "holdout_v1.json"
HUMANEVAL_PATH = ROOT / "memory" / "quizzes" / "hidden_humaneval.json"

PREAMBLE = "Write only Python, no markdown.\n\nImplement:\n\n"

MIN_ASSERTS = 6
MIN_MUTANTS = 15
MAX_MUTANTS = 22
MIN_MUTATION_SCORE = 0.90
REF_TIMEOUT = 20
MUTANT_TIMEOUT = 10


def _t(text: str) -> str:
    """Dedent a triple-quoted literal and trim the framing newlines."""
    return dedent(text).strip("\n")


def spec(
    id: str,
    title: str,
    difficulty: str,
    objective: str,
    holdout_test: str,
    reference: str,
) -> Dict[str, str]:
    """One task. `objective` is prompt-side; `reference` never leaves this file."""
    return {
        "id": id,
        "title": title,
        "difficulty": difficulty,
        "objective": PREAMBLE + _t(objective),
        "holdout_test": _t(holdout_test),
        "reference": _t(reference),
    }


def public_task(s: Dict[str, str]) -> Dict[str, str]:
    """The dataset row, assembled field by field.

    Deliberately NOT `{k: v for k, v in s.items() if k != "reference"}`: a
    filter is a denylist, and a denylist silently ships the next field someone
    adds. Naming the four public fields means an addition has to be made
    public on purpose.
    """
    return {
        "id": s["id"],
        "title": s["title"],
        "objective": s["objective"],
        "holdout_test": s["holdout_test"],
        "difficulty": s["difficulty"],
    }


# --------------------------------------------------------------------------
# The tasks
# --------------------------------------------------------------------------
#
# Every objective states a signature and describes behaviour. None of them
# contains a body, an assertion, or a worked example that duplicates something
# the holdout checks — the prose deliberately stops short of enumerating the
# cases, because a task that lists its own test cases measures reading, not
# programming.

SPECS: List[Dict[str, str]] = []

SPECS.append(spec(
    id="hr01",
    title="parse_roman",
    difficulty="hard",
    objective="""
    def parse_roman(s: str) -> int

    Convert a Roman numeral written in uppercase letters to the integer it
    denotes. The symbols are I=1, V=5, X=10, L=50, C=100, D=500, M=1000.

    Only the canonical spelling of a number is accepted. A string that happens
    to be readable by the usual left-to-right subtraction rule but is not the
    single conventional way to write its value must be rejected, as must any
    value outside the range 1 to 3999 inclusive.

    Raise ValueError for anything that is not a valid canonical numeral.
    """,
    holdout_test="""
    assert parse_roman('I') == 1
    assert parse_roman('IV') == 4
    assert parse_roman('IX') == 9
    assert parse_roman('XL') == 40
    assert parse_roman('LVIII') == 58
    assert parse_roman('CDXLIV') == 444
    assert parse_roman('MCMXCIV') == 1994
    assert parse_roman('MMMCMXCIX') == 3999
    assert parse_roman('MDCLXVI') == 1666
    assert parse_roman('XCIX') == 99
    _rejected = []
    for _s in ['', 'IIII', 'VV', 'IC', 'ABC', 'XM', 'IL', 'MMMM', 'iv', 'VX']:
        try:
            parse_roman(_s)
        except ValueError:
            _rejected.append(_s)
    assert _rejected == ['', 'IIII', 'VV', 'IC', 'ABC', 'XM', 'IL', 'MMMM', 'iv', 'VX']
    print('ok')
    """,
    reference="""
    def parse_roman(s):
        table = [
            (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
            (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
            (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I'),
        ]
        if not s:
            raise ValueError('empty roman numeral')
        total = 0
        pos = 0
        for value, symbol in table:
            count = 0
            while s[pos:pos + len(symbol)] == symbol:
                count += 1
                pos += len(symbol)
                total += value
            limit = 3 if symbol in ('M', 'C', 'X', 'I') else 1
            if count > limit:
                raise ValueError('not canonical')
        if pos != len(s):
            raise ValueError('unparsed trailing symbols')
        return total
    """,
))

SPECS.append(spec(
    id="hr02",
    title="int_to_roman",
    difficulty="medium",
    objective="""
    def int_to_roman(n: int) -> str

    Return the canonical uppercase Roman numeral for n, using the symbols
    I=1, V=5, X=10, L=50, C=100, D=500, M=1000 and the conventional
    subtractive forms rather than four repeated symbols.

    Only integers from 1 to 3999 inclusive can be written this way; anything
    else must raise ValueError.
    """,
    holdout_test="""
    assert int_to_roman(1) == 'I'
    assert int_to_roman(4) == 'IV'
    assert int_to_roman(9) == 'IX'
    assert int_to_roman(14) == 'XIV'
    assert int_to_roman(40) == 'XL'
    assert int_to_roman(90) == 'XC'
    assert int_to_roman(400) == 'CD'
    assert int_to_roman(944) == 'CMXLIV'
    assert int_to_roman(3999) == 'MMMCMXCIX'
    assert int_to_roman(1000) == 'M'
    _rejected = []
    for _n in [0, -1, 4000, 10000]:
        try:
            int_to_roman(_n)
        except ValueError:
            _rejected.append(_n)
    assert _rejected == [0, -1, 4000, 10000]
    print('ok')
    """,
    reference="""
    def int_to_roman(n):
        table = [
            (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
            (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
            (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I'),
        ]
        if n < 1 or n > 3999:
            raise ValueError('out of range')
        out = []
        for value, symbol in table:
            while n >= value:
                out.append(symbol)
                n -= value
        return ''.join(out)
    """,
))

SPECS.append(spec(
    id="hr03",
    title="merge_intervals",
    difficulty="hard",
    objective="""
    def merge_intervals(intervals: list) -> list

    Each element of intervals is a two-element list [start, end] with
    start <= end. Return the shortest list of intervals that covers exactly the
    same points, sorted by start. Two intervals that share only an endpoint are
    treated as overlapping and must be combined.

    The argument is read-only: neither the outer list nor any inner list may be
    modified, and the returned intervals must be fresh lists that the caller can
    mutate without affecting the input.
    """,
    holdout_test="""
    _src = [[1, 3], [2, 6], [8, 10], [15, 18]]
    _before = [list(x) for x in _src]
    assert merge_intervals(_src) == [[1, 6], [8, 10], [15, 18]]
    assert _src == _before
    assert merge_intervals([]) == []
    assert merge_intervals([[1, 4], [4, 5]]) == [[1, 5]]
    assert merge_intervals([[5, 6], [1, 2]]) == [[1, 2], [5, 6]]
    assert merge_intervals([[1, 10], [2, 3], [4, 5]]) == [[1, 10]]
    assert merge_intervals([[2, 2], [2, 2]]) == [[2, 2]]
    assert merge_intervals([[1, 4], [0, 4]]) == [[0, 4]]
    assert merge_intervals([[1, 4], [2, 3]]) == [[1, 4]]
    assert merge_intervals([[1, 3], [5, 7], [6, 9]]) == [[1, 3], [5, 9]]
    assert merge_intervals([[1, 3], [5, 20], [6, 9]]) == [[1, 3], [5, 20]]
    assert merge_intervals([[1, 3], [5, 7], [2, 4]]) == [[1, 4], [5, 7]]
    _out = merge_intervals(_src)
    _out[0][0] = 99
    assert _src[0][0] == 1
    print('ok')
    """,
    reference="""
    def merge_intervals(intervals):
        ordered = sorted((list(iv) for iv in intervals), key=lambda iv: (iv[0], iv[1]))
        out = []
        for start, end in ordered:
            if out and start <= out[-1][1]:
                out[-1][1] = max(out[-1][1], end)
            else:
                out.append([start, end])
        return out
    """,
))

SPECS.append(spec(
    id="hr04",
    title="summarize_ranges",
    difficulty="medium",
    objective="""
    def summarize_ranges(nums: list) -> list

    nums is a list of integers in strictly ascending order. Collapse it into a
    list of strings, one per maximal run of consecutive integers: a run of two
    or more becomes the first and last value joined by '->', and a value with
    no neighbour stands alone as its own decimal string.

    Negative values participate in runs like any other. nums must not be
    modified.
    """,
    holdout_test="""
    assert summarize_ranges([]) == []
    assert summarize_ranges([5]) == ['5']
    assert summarize_ranges([0, 1, 2, 4, 5, 7]) == ['0->2', '4->5', '7']
    assert summarize_ranges([-3, -2, -1, 2]) == ['-3->-1', '2']
    assert summarize_ranges([1, 3, 5]) == ['1', '3', '5']
    assert summarize_ranges([-1, 0, 1]) == ['-1->1']
    assert summarize_ranges([7, 8]) == ['7->8']
    assert summarize_ranges([1, 2, 4]) == ['1->2', '4']
    _in = [1, 2, 3]
    summarize_ranges(_in)
    assert _in == [1, 2, 3]
    print('ok')
    """,
    reference="""
    def summarize_ranges(nums):
        out = []
        i = 0
        n = len(nums)
        while i < n:
            j = i
            while j + 1 < n and nums[j + 1] == nums[j] + 1:
                j += 1
            if j > i:
                out.append(str(nums[i]) + '->' + str(nums[j]))
            else:
                out.append(str(nums[i]))
            i = j + 1
        return out
    """,
))

SPECS.append(spec(
    id="hr05",
    title="LRUCache",
    difficulty="hard",
    objective="""
    class LRUCache:
        def __init__(self, capacity: int)
        def get(self, key)
        def put(self, key, value) -> None
        def keys(self) -> list
        def __len__(self) -> int

    A fixed-size cache that discards the least recently used entry when it has
    to make room. get() returns the stored value, or None when the key is
    absent. Both a successful get() and a put() count as a use of that key,
    including a put() that overwrites a key already present — an overwrite
    updates the value without growing the cache. Once the cache holds
    `capacity` entries, storing a new key evicts whichever key has gone longest
    without a use.

    keys() reports the keys currently held, least recently used first. len()
    reports how many are held. A capacity that is not a positive integer is
    meaningless and must raise ValueError.
    """,
    holdout_test="""
    _bad = []
    for _c in [0, -1]:
        try:
            LRUCache(_c)
        except ValueError:
            _bad.append(_c)
    assert _bad == [0, -1]
    c = LRUCache(2)
    c.put('a', 1)
    c.put('b', 2)
    assert c.get('a') == 1
    c.put('c', 3)
    assert c.get('b') is None
    assert c.keys() == ['a', 'c']
    assert len(c) == 2
    c.put('a', 10)
    assert c.keys() == ['c', 'a']
    assert c.get('a') == 10
    assert len(c) == 2
    d = LRUCache(1)
    d.put('x', 1)
    d.put('y', 2)
    assert d.keys() == ['y']
    assert d.get('x') is None
    assert len(d) == 1
    e = LRUCache(3)
    e.put('p', 1)
    e.put('q', 2)
    e.put('r', 3)
    assert e.get('p') == 1
    e.put('s', 4)
    assert e.keys() == ['r', 'p', 's']
    print('ok')
    """,
    reference="""
    class LRUCache:
        def __init__(self, capacity):
            if not isinstance(capacity, int) or capacity < 1:
                raise ValueError('capacity must be a positive integer')
            self.capacity = capacity
            self._data = {}

        def get(self, key):
            if key not in self._data:
                return None
            value = self._data.pop(key)
            self._data[key] = value
            return value

        def put(self, key, value):
            if key in self._data:
                self._data.pop(key)
            elif len(self._data) >= self.capacity:
                oldest = next(iter(self._data))
                self._data.pop(oldest)
            self._data[key] = value

        def keys(self):
            return list(self._data)

        def __len__(self):
            return len(self._data)
    """,
))

SPECS.append(spec(
    id="hr06",
    title="CircularBuffer",
    difficulty="hard",
    objective="""
    class CircularBuffer:
        def __init__(self, capacity: int)
        def push(self, item) -> None
        def pop(self)
        def to_list(self) -> list
        def is_full(self) -> bool
        def __len__(self) -> int

    A queue of bounded size. push() appends an item; when the buffer is
    already at capacity the oldest item is silently discarded to make room, so
    a push never fails and never grows the buffer past its capacity. pop()
    removes and returns the oldest item, and raises IndexError when there is
    nothing to remove.

    to_list() returns the contents oldest first, as a list the caller may
    modify without affecting the buffer. is_full() answers whether another
    push would displace anything. A capacity that is not a positive integer
    must raise ValueError.
    """,
    holdout_test="""
    _bad = []
    for _c in [0, -1]:
        try:
            CircularBuffer(_c)
        except ValueError:
            _bad.append(_c)
    assert _bad == [0, -1]
    b = CircularBuffer(3)
    assert len(b) == 0
    assert b.to_list() == []
    assert b.is_full() is False
    b.push(1)
    b.push(2)
    assert b.is_full() is False
    b.push(3)
    assert b.is_full() is True
    assert b.to_list() == [1, 2, 3]
    b.push(4)
    assert b.to_list() == [2, 3, 4]
    assert len(b) == 3
    assert b.pop() == 2
    assert b.is_full() is False
    assert b.to_list() == [3, 4]
    b.push(5)
    b.push(6)
    assert b.to_list() == [4, 5, 6]
    _snapshot = b.to_list()
    _snapshot.append(99)
    assert len(b) == 3
    assert b.pop() == 4
    assert b.pop() == 5
    assert b.pop() == 6
    _err = None
    try:
        b.pop()
    except IndexError:
        _err = 'IndexError'
    assert _err == 'IndexError'
    one = CircularBuffer(1)
    one.push('a')
    one.push('b')
    assert one.to_list() == ['b']
    print('ok')
    """,
    reference="""
    class CircularBuffer:
        def __init__(self, capacity):
            if not isinstance(capacity, int) or capacity < 1:
                raise ValueError('capacity must be a positive integer')
            self.capacity = capacity
            self._items = []

        def push(self, item):
            if len(self._items) >= self.capacity:
                self._items.pop(0)
            self._items.append(item)

        def pop(self):
            return self._items.pop(0)

        def to_list(self):
            return list(self._items)

        def is_full(self):
            return len(self._items) >= self.capacity

        def __len__(self):
            return len(self._items)
    """,
))

SPECS.append(spec(
    id="hr07",
    title="RunningMedian",
    difficulty="hard",
    objective="""
    class RunningMedian:
        def add(self, x) -> None
        def median(self)
        def __len__(self) -> int

    Track numbers as they arrive and report the median of everything added so
    far. With an odd count the median is the middle value; with an even count
    it is the arithmetic mean of the two middle values. Values may arrive in
    any order, may repeat, and may be negative.

    Asking for the median before anything has been added has no answer and
    must raise ValueError. The constructor takes no arguments.
    """,
    holdout_test="""
    m = RunningMedian()
    assert len(m) == 0
    _err = None
    try:
        m.median()
    except ValueError:
        _err = 'ValueError'
    assert _err == 'ValueError'
    m.add(5)
    assert m.median() == 5
    m.add(1)
    assert m.median() == 3.0
    m.add(3)
    assert m.median() == 3
    m.add(3)
    assert m.median() == 3.0
    m.add(-10)
    m.add(100)
    assert len(m) == 6
    assert m.median() == 3.0
    n = RunningMedian()
    n.add(2)
    n.add(4)
    assert n.median() == 3.0
    n.add(1)
    assert n.median() == 2
    assert len(n) == 3
    p = RunningMedian()
    p.add(-1)
    p.add(-3)
    assert p.median() == -2.0
    h = RunningMedian()
    h.add(1)
    h.add(2)
    assert h.median() == 1.5
    h.add(-4)
    h.add(-5)
    assert h.median() == -1.5
    print('ok')
    """,
    reference="""
    class RunningMedian:
        def __init__(self):
            self._values = []

        def add(self, x):
            self._values.append(x)

        def median(self):
            if not self._values:
                raise ValueError('no values yet')
            ordered = sorted(self._values)
            n = len(ordered)
            mid = n // 2
            if n % 2 == 1:
                return ordered[mid]
            return (ordered[mid - 1] + ordered[mid]) / 2

        def __len__(self):
            return len(self._values)
    """,
))

SPECS.append(spec(
    id="hr08",
    title="TaskQueue",
    difficulty="hard",
    objective="""
    class TaskQueue:
        def push(self, name: str, priority: int) -> None
        def pop(self) -> str
        def peek(self)
        def __len__(self) -> int

    A priority queue over task names. A larger priority number means more
    urgent, and priorities may be negative. pop() removes and returns the name
    of the most urgent task; when several share the highest priority the one
    pushed earliest wins, so equal-priority tasks come back in the order they
    arrived. peek() reports the name pop() would return without removing it,
    and returns None when nothing is queued.

    pop() on an empty queue must raise IndexError. The same name may be pushed
    more than once. The constructor takes no arguments.
    """,
    holdout_test="""
    q = TaskQueue()
    assert len(q) == 0
    assert q.peek() is None
    _err = None
    try:
        q.pop()
    except IndexError:
        _err = 'IndexError'
    assert _err == 'IndexError'
    q.push('a', 1)
    q.push('b', 5)
    q.push('c', 5)
    q.push('d', 0)
    assert len(q) == 4
    assert q.peek() == 'b'
    assert q.pop() == 'b'
    assert q.pop() == 'c'
    assert q.peek() == 'a'
    assert q.pop() == 'a'
    assert q.pop() == 'd'
    assert len(q) == 0
    r = TaskQueue()
    r.push('x', -3)
    r.push('y', -1)
    assert r.pop() == 'y'
    assert r.peek() == 'x'
    assert len(r) == 1
    s = TaskQueue()
    s.push('dup', 2)
    s.push('dup', 9)
    assert s.pop() == 'dup'
    assert s.pop() == 'dup'
    assert len(s) == 0
    print('ok')
    """,
    reference="""
    class TaskQueue:
        def __init__(self):
            self._entries = []

        def push(self, name, priority):
            self._entries.append((priority, name))

        def _best_index(self):
            best = 0
            for i, entry in enumerate(self._entries):
                if entry[0] > self._entries[best][0]:
                    best = i
            return best

        def peek(self):
            if not self._entries:
                return None
            return self._entries[self._best_index()][1]

        def pop(self):
            if not self._entries:
                raise IndexError('pop from an empty queue')
            return self._entries.pop(self._best_index())[1]

        def __len__(self):
            return len(self._entries)
    """,
))

SPECS.append(spec(
    id="hr09",
    title="spiral_order",
    difficulty="hard",
    objective="""
    def spiral_order(grid: list) -> list

    grid is a rectangular list of rows, every row the same length. Return a
    flat list of its values visited in a clockwise spiral: along the top row
    left to right, down the right edge, back along the bottom row, up the left
    edge, then inward and around again until every value has been visited
    exactly once.

    Grids with no rows, or with rows that hold no values, produce an empty
    list. Grids that are one row or one column tall are still valid. grid must
    not be modified.
    """,
    holdout_test="""
    assert spiral_order([]) == []
    assert spiral_order([[]]) == []
    assert spiral_order([[1]]) == [1]
    assert spiral_order([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == [1, 2, 3, 6, 9, 8, 7, 4, 5]
    assert spiral_order([[1, 2, 3, 4]]) == [1, 2, 3, 4]
    assert spiral_order([[1], [2], [3]]) == [1, 2, 3]
    assert spiral_order([[1, 2], [3, 4], [5, 6]]) == [1, 2, 4, 6, 5, 3]
    assert spiral_order([[1, 2, 3], [4, 5, 6]]) == [1, 2, 3, 6, 5, 4]
    assert spiral_order([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]) == [
        1, 2, 3, 4, 8, 12, 11, 10, 9, 5, 6, 7]
    _g = [[1, 2], [3, 4]]
    assert spiral_order(_g) == [1, 2, 4, 3]
    assert _g == [[1, 2], [3, 4]]
    print('ok')
    """,
    reference="""
    def spiral_order(grid):
        if not grid or not grid[0]:
            return []
        top = 0
        bottom = len(grid) - 1
        left = 0
        right = len(grid[0]) - 1
        out = []
        while top <= bottom and left <= right:
            for col in range(left, right + 1):
                out.append(grid[top][col])
            top += 1
            for row in range(top, bottom + 1):
                out.append(grid[row][right])
            right -= 1
            if top <= bottom:
                for col in range(right, left - 1, -1):
                    out.append(grid[bottom][col])
                bottom -= 1
            if left <= right:
                for row in range(bottom, top - 1, -1):
                    out.append(grid[row][left])
                left += 1
        return out
    """,
))

SPECS.append(spec(
    id="hr10",
    title="rotate_grid",
    difficulty="medium",
    objective="""
    def rotate_grid(grid: list, turns: int = 1) -> list

    Rotate a rectangular grid clockwise by `turns` quarter turns and return the
    result. A rotated non-square grid changes shape: an r-by-c grid becomes
    c-by-r. `turns` may be zero, negative (anticlockwise) or larger than four,
    and only its effect modulo a full revolution matters.

    The result must be built from fresh rows: neither grid nor any of its rows
    may be modified, and mutating the returned grid must not disturb the
    argument — including when the rotation happens to be the identity. A grid
    with no rows rotates to a grid with no rows.
    """,
    holdout_test="""
    _g = [[1, 2], [3, 4]]
    assert rotate_grid(_g) == [[3, 1], [4, 2]]
    assert _g == [[1, 2], [3, 4]]
    assert rotate_grid(_g, 2) == [[4, 3], [2, 1]]
    assert rotate_grid(_g, 3) == [[2, 4], [1, 3]]
    assert rotate_grid(_g, 4) == [[1, 2], [3, 4]]
    assert rotate_grid(_g, 0) == [[1, 2], [3, 4]]
    assert rotate_grid(_g, -1) == [[2, 4], [1, 3]]
    assert rotate_grid(_g, 5) == [[3, 1], [4, 2]]
    assert rotate_grid([[1, 2, 3]]) == [[1], [2], [3]]
    assert rotate_grid([[1, 2, 3]], -1) == [[3], [2], [1]]
    assert rotate_grid([]) == []
    _out = rotate_grid(_g, 4)
    _out[0][0] = 99
    assert _g[0][0] == 1
    print('ok')
    """,
    reference="""
    def rotate_grid(grid, turns=1):
        out = [list(row) for row in grid]
        for _ in range(turns % 4):
            rows = len(out)
            cols = len(out[0]) if out else 0
            out = [[out[rows - 1 - r][c] for r in range(rows)] for c in range(cols)]
        return out
    """,
))

SPECS.append(spec(
    id="hr11",
    title="to_base",
    difficulty="medium",
    objective="""
    def to_base(n: int, base: int) -> str

    Render the integer n in the given base as a string, using the digits 0-9
    followed by the lowercase letters a-z for digit values ten and above. The
    representation carries no leading zeros, except that zero itself is a
    single '0'. A negative n is rendered as '-' followed by the rendering of
    its magnitude.

    Only bases from 2 to 36 inclusive can be written with those digits;
    anything else must raise ValueError.
    """,
    holdout_test="""
    assert to_base(0, 2) == '0'
    assert to_base(0, 36) == '0'
    assert to_base(10, 2) == '1010'
    assert to_base(255, 16) == 'ff'
    assert to_base(-255, 16) == '-ff'
    assert to_base(35, 36) == 'z'
    assert to_base(36, 36) == '10'
    assert to_base(7, 10) == '7'
    assert to_base(-1, 2) == '-1'
    assert to_base(4095, 16) == 'fff'
    assert to_base(8, 8) == '10'
    _rejected = []
    for _b in [1, 0, 37, -2]:
        try:
            to_base(5, _b)
        except ValueError:
            _rejected.append(_b)
    assert _rejected == [1, 0, 37, -2]
    print('ok')
    """,
    reference="""
    def to_base(n, base):
        if base < 2 or base > 36:
            raise ValueError('base must be between 2 and 36')
        digits = '0123456789abcdefghijklmnopqrstuvwxyz'
        negative = n < 0
        n = abs(n)
        out = []
        while n:
            out.append(digits[n % base])
            n //= base
        if not out:
            out.append(digits[0])
        if negative:
            out.append('-')
        return ''.join(reversed(out))
    """,
))

SPECS.append(spec(
    id="hr12",
    title="top_k_frequent",
    difficulty="medium",
    objective="""
    def top_k_frequent(items: list, k: int) -> list

    Return the k items that occur most often in items as a list of
    (item, count) tuples, most frequent first. Items that occur equally often
    are ordered by where they first appear in items, so the result is fully
    determined by the input and never depends on hash order.

    Asking for no items, or for a negative number of them, yields an empty
    list; asking for more than there are distinct items yields all of them.
    items must not be modified.
    """,
    holdout_test="""
    assert top_k_frequent([], 3) == []
    assert top_k_frequent(['a', 'b', 'a', 'c', 'b', 'a'], 2) == [('a', 3), ('b', 2)]
    assert top_k_frequent(['b', 'a'], 2) == [('b', 1), ('a', 1)]
    assert top_k_frequent(['a', 'b', 'c'], 5) == [('a', 1), ('b', 1), ('c', 1)]
    assert top_k_frequent(['a', 'a', 'b', 'b', 'c'], 0) == []
    assert top_k_frequent(['a', 'a', 'b', 'b', 'c'], -1) == []
    assert top_k_frequent([1, 1, 2, 2, 3, 3, 3], 2) == [(3, 3), (1, 2)]
    assert top_k_frequent(['z', 'y', 'y', 'z', 'x'], 3) == [('z', 2), ('y', 2), ('x', 1)]
    assert top_k_frequent(['a', 'b', 'a'], 1) == [('a', 2)]
    _in = ['x', 'y', 'x']
    top_k_frequent(_in, 1)
    assert _in == ['x', 'y', 'x']
    print('ok')
    """,
    reference="""
    def top_k_frequent(items, k):
        if k < 1:
            return []
        counts = {}
        first = {}
        for index, item in enumerate(items):
            if item in counts:
                counts[item] += 1
            else:
                counts[item] = 1
                first[item] = index
        ordered = sorted(counts, key=lambda item: (-counts[item], first[item]))
        return [(item, counts[item]) for item in ordered[:k]]
    """,
))

SPECS.append(spec(
    id="hr13",
    title="validate_ipv4",
    difficulty="medium",
    objective="""
    def validate_ipv4(s: str) -> bool

    Report whether s is a well-formed dotted-quad IPv4 address and nothing
    else. A well-formed address is exactly four parts separated by dots, each
    part written in decimal digits only, each denoting a value from 0 to 255,
    and none carrying a redundant leading zero.

    Anything else — the wrong number of parts, an empty part, a sign, spaces
    or other surrounding characters — is not an address. The function returns
    a bool, never raises for a str input.
    """,
    holdout_test="""
    assert validate_ipv4('0.0.0.0') is True
    assert validate_ipv4('255.255.255.255') is True
    assert validate_ipv4('192.168.1.1') is True
    assert validate_ipv4('1.2.3.0') is True
    assert validate_ipv4('256.1.1.1') is False
    assert validate_ipv4('01.2.3.4') is False
    assert validate_ipv4('1.2.3') is False
    assert validate_ipv4('1.2.3.4.5') is False
    assert validate_ipv4(' 1.2.3.4') is False
    assert validate_ipv4('1.2.3.4 ') is False
    assert validate_ipv4('1.2.3.') is False
    assert validate_ipv4('1.2.3.+4') is False
    assert validate_ipv4('1.2.3.-4') is False
    assert validate_ipv4('') is False
    assert validate_ipv4('1.2.3.00') is False
    assert validate_ipv4('...') is False
    print('ok')
    """,
    reference="""
    def validate_ipv4(s):
        parts = s.split('.')
        if len(parts) != 4:
            return False
        for part in parts:
            if not part:
                return False
            for ch in part:
                if ch not in '0123456789':
                    return False
            if len(part) > 1 and part[0] == '0':
                return False
            if int(part) > 255:
                return False
        return True
    """,
))

SPECS.append(spec(
    id="hr14",
    title="chunk_evenly",
    difficulty="medium",
    objective="""
    def chunk_evenly(items: list, n: int) -> list

    Split items into exactly n contiguous chunks whose sizes differ by at most
    one, with the larger chunks first, preserving the original order. When
    there are fewer items than chunks the trailing chunks come out empty.

    Every returned chunk is a new list, and items itself is not modified. An n
    that is not a positive integer cannot describe a split and must raise
    ValueError.
    """,
    holdout_test="""
    assert chunk_evenly([1, 2, 3, 4, 5], 2) == [[1, 2, 3], [4, 5]]
    assert chunk_evenly([1, 2, 3, 4, 5, 6], 3) == [[1, 2], [3, 4], [5, 6]]
    assert chunk_evenly([1, 2, 3], 1) == [[1, 2, 3]]
    assert chunk_evenly([], 3) == [[], [], []]
    assert chunk_evenly([1, 2], 3) == [[1], [2], []]
    assert chunk_evenly([1, 2, 3, 4, 5, 6, 7], 3) == [[1, 2, 3], [4, 5], [6, 7]]
    assert chunk_evenly([1, 2, 3, 4], 4) == [[1], [2], [3], [4]]
    assert chunk_evenly([1, 2, 3, 4, 5], 4) == [[1, 2], [3], [4], [5]]
    _rejected = []
    for _n in [0, -1]:
        try:
            chunk_evenly([1], _n)
        except ValueError:
            _rejected.append(_n)
    assert _rejected == [0, -1]
    _src = [1, 2, 3]
    _out = chunk_evenly(_src, 2)
    _out[0].append(9)
    assert _src == [1, 2, 3]
    print('ok')
    """,
    reference="""
    def chunk_evenly(items, n):
        if not isinstance(n, int) or n < 1:
            raise ValueError('n must be a positive integer')
        size, extra = divmod(len(items), n)
        out = []
        start = 0
        for i in range(n):
            width = size + 1 if i < extra else size
            out.append(list(items[start:start + width]))
            start += width
        return out
    """,
))

SPECS.append(spec(
    id="hr15",
    title="eval_rpn",
    difficulty="hard",
    objective="""
    def eval_rpn(tokens: list) -> int

    Evaluate a list of tokens in reverse Polish notation and return the
    integer result. Operand tokens are strings holding a decimal integer,
    possibly negative. Operator tokens are '+', '-', '*' and '/', each
    consuming the two operands most recently produced, in the order they were
    pushed.

    Division is integer division that truncates toward zero, so it discards
    the fractional part rather than rounding down. Dividing by zero must raise
    ZeroDivisionError. Any expression that is not well formed — an operator
    without enough operands, an unknown token, or operands left over at the
    end — must raise ValueError.
    """,
    holdout_test="""
    assert eval_rpn(['5']) == 5
    assert eval_rpn(['2', '3', '+']) == 5
    assert eval_rpn(['3', '4', '-']) == -1
    assert eval_rpn(['4', '2', '/']) == 2
    assert eval_rpn(['-7', '2', '/']) == -3
    assert eval_rpn(['7', '-2', '/']) == -3
    assert eval_rpn(['-7', '-2', '/']) == 3
    assert eval_rpn(['2', '3', '4', '*', '+']) == 14
    assert eval_rpn(['5', '1', '2', '+', '4', '*', '+', '3', '-']) == 14
    assert eval_rpn(['6', '3', '*']) == 18
    _zero = None
    try:
        eval_rpn(['1', '0', '/'])
    except ZeroDivisionError:
        _zero = 'ZeroDivisionError'
    assert _zero == 'ZeroDivisionError'
    _bad = 0
    for _t in [[], ['+'], ['1', '2'], ['1', '2', '^'], ['1', '+']]:
        try:
            eval_rpn(_t)
        except ValueError:
            _bad += 1
    assert _bad == 5
    print('ok')
    """,
    reference="""
    def eval_rpn(tokens):
        stack = []
        for token in tokens:
            if token in ('+', '-', '*', '/'):
                if len(stack) < 2:
                    raise ValueError('not enough operands')
                b = stack.pop()
                a = stack.pop()
                if token == '+':
                    stack.append(a + b)
                elif token == '-':
                    stack.append(a - b)
                elif token == '*':
                    stack.append(a * b)
                else:
                    stack.append(int(a / b))
            else:
                try:
                    stack.append(int(token))
                except ValueError:
                    raise ValueError('unknown token')
        if len(stack) != 1:
            raise ValueError('malformed expression')
        return stack.pop()
    """,
))

SPECS.append(spec(
    id="hr16",
    title="eval_infix",
    difficulty="hard",
    objective="""
    def eval_infix(expr: str) -> float

    Evaluate an ordinary arithmetic expression written as a string and return
    the result as a float. The expression may use +, -, * and / between
    non-negative decimal numbers, and parentheses to group. Multiplication and
    division bind tighter than addition and subtraction; operators of equal
    precedence associate to the left. Division is true division, not integer
    division. Whitespace anywhere is insignificant.

    Dividing by zero must raise ZeroDivisionError. Anything that is not a
    complete, well-formed expression — including an empty string, a dangling
    operator, unbalanced parentheses, an empty pair of parentheses, or a
    character with no meaning here — must raise ValueError.
    """,
    holdout_test="""
    assert eval_infix('1+2*3') == 7.0
    assert eval_infix('(1+2)*3') == 9.0
    assert eval_infix(' 2 * ( 3 + 4 ) / 7 ') == 2.0
    assert eval_infix('10-2-3') == 5.0
    assert eval_infix('100/10/2') == 5.0
    assert eval_infix('2.5*4') == 10.0
    assert eval_infix('7') == 7.0
    assert eval_infix('((2))') == 2.0
    assert eval_infix('1/8') == 0.125
    assert eval_infix('1 2') == 12.0
    assert isinstance(eval_infix('1+1'), float)
    _zero = None
    try:
        eval_infix('1/0')
    except ZeroDivisionError:
        _zero = 'ZeroDivisionError'
    assert _zero == 'ZeroDivisionError'
    _bad = 0
    for _s in ['', '1+', '(1+2', '1+2)', 'a+1', '()', '*3', '1..2', '1*/2']:
        try:
            eval_infix(_s)
        except ValueError:
            _bad += 1
    assert _bad == 9
    print('ok')
    """,
    reference="""
    def eval_infix(expr):
        text = ''.join(expr.split())
        tokens = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch in '+-*/()':
                tokens.append(ch)
                i += 1
            elif ch.isdigit() or ch == '.':
                j = i
                while j < len(text) and (text[j].isdigit() or text[j] == '.'):
                    j += 1
                try:
                    tokens.append(float(text[i:j]))
                except ValueError:
                    raise ValueError('malformed number')
                i = j
            else:
                raise ValueError('unexpected character')
        pos = [0]

        def peek():
            if pos[0] < len(tokens):
                return tokens[pos[0]]
            return None

        def factor():
            token = peek()
            if token == '(':
                pos[0] += 1
                value = expression()
                if peek() != ')':
                    raise ValueError('unbalanced parentheses')
                pos[0] += 1
                return value
            if isinstance(token, float):
                pos[0] += 1
                return token
            raise ValueError('expected a number')

        def term():
            value = factor()
            while peek() in ('*', '/'):
                op = tokens[pos[0]]
                pos[0] += 1
                right = factor()
                if op == '*':
                    value = value * right
                else:
                    if right == 0:
                        raise ZeroDivisionError('division by zero')
                    value = value / right
            return value

        def expression():
            value = term()
            while peek() in ('+', '-'):
                op = tokens[pos[0]]
                pos[0] += 1
                right = term()
                if op == '+':
                    value = value + right
                else:
                    value = value - right
            return value

        result = expression()
        if pos[0] != len(tokens):
            raise ValueError('trailing input')
        return float(result)
    """,
))

SPECS.append(spec(
    id="hr17",
    title="min_coins",
    difficulty="hard",
    objective="""
    def min_coins(coins: list, amount: int) -> int

    Return the smallest number of coins whose values add up to exactly
    `amount`. Each value in coins is a positive integer and may be used as
    many times as you like; the list may repeat a value, which changes
    nothing. An amount of zero needs no coins.

    Not every amount is reachable from every set of coins; when none exists,
    return -1. A negative amount is not a request that can be answered and
    must raise ValueError.

    Note that repeatedly taking the largest coin that still fits does not
    always give the fewest coins.
    """,
    holdout_test="""
    assert min_coins([1, 3, 4], 6) == 2
    assert min_coins([2], 3) == -1
    assert min_coins([1, 2, 5], 11) == 3
    assert min_coins([], 0) == 0
    assert min_coins([], 5) == -1
    assert min_coins([5, 5, 5], 10) == 2
    assert min_coins([9, 6, 5, 1], 11) == 2
    assert min_coins([1], 0) == 0
    assert min_coins([7, 2], 13) == 4
    assert min_coins([3], 3) == 1
    assert min_coins([25, 10, 4], 41) == 5
    assert min_coins([1, 5], 1) == 1
    _err = None
    try:
        min_coins([1], -1)
    except ValueError:
        _err = 'ValueError'
    assert _err == 'ValueError'
    print('ok')
    """,
    reference="""
    def min_coins(coins, amount):
        if amount < 0:
            raise ValueError('amount must not be negative')
        best = [0] + [None] * amount
        for step in range(amount):
            target = step + 1
            for coin in coins:
                if coin > target:
                    continue
                previous = best[target - coin]
                if previous is None:
                    continue
                if best[target] is None or previous + 1 < best[target]:
                    best[target] = previous + 1
        if best[amount] is None:
            return -1
        return best[amount]
    """,
))

SPECS.append(spec(
    id="hr18",
    title="best_value",
    difficulty="hard",
    objective="""
    def best_value(items: list, capacity: int) -> int

    Each element of items is a (weight, value) pair of positive integers.
    Choose a subset whose total weight does not exceed capacity and whose
    total value is as large as possible, and return that total value. Each
    item is available once only — it cannot be taken twice or in part.

    With nothing to choose from, or with no capacity to spend, the best total
    is zero. A negative capacity is not a meaningful budget and must raise
    ValueError.

    Note that taking items in order of value per unit weight does not always
    give the best total.
    """,
    holdout_test="""
    assert best_value([], 10) == 0
    assert best_value([(1, 1)], 0) == 0
    assert best_value([(5, 10)], 4) == 0
    assert best_value([(5, 10)], 5) == 10
    assert best_value([(3, 4), (4, 5), (2, 3)], 6) == 8
    assert best_value([(1, 1), (1, 1), (1, 1)], 2) == 2
    assert best_value([(2, 3), (2, 3)], 4) == 6
    assert best_value([(10, 60), (20, 100), (30, 120)], 50) == 220
    assert best_value([(1, 5), (1, 5)], 1) == 5
    assert best_value([(4, 7)], 10) == 7
    _err = None
    try:
        best_value([], -1)
    except ValueError:
        _err = 'ValueError'
    assert _err == 'ValueError'
    print('ok')
    """,
    reference="""
    def best_value(items, capacity):
        if capacity < 0:
            raise ValueError('capacity must not be negative')
        best = [0] * (capacity + 1)
        for weight, value in items:
            for room in range(capacity, weight - 1, -1):
                best[room] = max(best[room], best[room - weight] + value)
        return best[capacity]
    """,
))

SPECS.append(spec(
    id="hr19",
    title="min_rooms",
    difficulty="medium",
    objective="""
    def min_rooms(meetings: list) -> int

    Each element of meetings is a (start, end) pair of numbers with
    start < end, describing a half-open interval: the room is occupied from
    start up to but not including end. Return the smallest number of rooms
    that could host every meeting without two meetings sharing a room at the
    same instant.

    Meetings arrive in no particular order, may be identical, and a meeting
    that begins exactly when another ends can reuse its room. With no meetings
    no rooms are needed. meetings must not be modified.
    """,
    holdout_test="""
    assert min_rooms([]) == 0
    assert min_rooms([(1, 5)]) == 1
    assert min_rooms([(0, 30), (5, 10), (15, 20)]) == 2
    assert min_rooms([(7, 10), (2, 4)]) == 1
    assert min_rooms([(0, 1), (1, 2), (2, 3)]) == 1
    assert min_rooms([(1, 5), (1, 5), (1, 5)]) == 3
    assert min_rooms([(1, 10), (2, 7), (3, 19), (8, 12), (10, 20), (11, 30)]) == 4
    assert min_rooms([(0, 2), (1, 3), (2, 4)]) == 2
    assert min_rooms([(1, 2), (0, 1)]) == 1
    assert min_rooms([(2, 3), (1, 2), (0, 1)]) == 1
    _m = [(0, 2), (1, 3)]
    assert min_rooms(_m) == 2
    assert _m == [(0, 2), (1, 3)]
    print('ok')
    """,
    reference="""
    def min_rooms(meetings):
        events = []
        for start, end in meetings:
            events.append((start, 1))
            events.append((end, -1))
        events.sort(key=lambda event: (event[0], event[1]))
        current = 0
        peak = 0
        for _, delta in events:
            current += delta
            peak = max(peak, current)
        return peak
    """,
))

SPECS.append(spec(
    id="hr20",
    title="compare_versions",
    difficulty="medium",
    objective="""
    def compare_versions(a: str, b: str) -> int

    Compare two dot-separated version strings and return -1 if a orders before
    b, 1 if it orders after, and 0 if they denote the same version. Each
    component is compared as a number, not as text, and the two versions need
    not have the same number of components — a version with fewer components
    is treated as having zeros beyond its end. A component may carry leading
    zeros.

    A string with an empty component, or a component that is not written in
    decimal digits, is not a version and must raise ValueError.
    """,
    holdout_test="""
    assert compare_versions('1.0', '1') == 0
    assert compare_versions('1.10', '1.9') == 1
    assert compare_versions('1.01', '1.1') == 0
    assert compare_versions('0.1', '1.0') == -1
    assert compare_versions('1.0.0.0', '1') == 0
    assert compare_versions('2', '1.9.9') == 1
    assert compare_versions('1.2.3', '1.2.3') == 0
    assert compare_versions('1.0.1', '1') == 1
    assert compare_versions('1', '1.0.1') == -1
    assert compare_versions('0', '0.0') == 0
    _bad = 0
    for _a, _b in [('1..2', '1'), ('', '1'), ('1.a', '1'), ('1', '1.-2'), ('1', '')]:
        try:
            compare_versions(_a, _b)
        except ValueError:
            _bad += 1
    assert _bad == 5
    print('ok')
    """,
    reference="""
    def compare_versions(a, b):
        def parse(text):
            out = []
            for chunk in text.split('.'):
                if not chunk:
                    raise ValueError('empty component')
                for ch in chunk:
                    if ch not in '0123456789':
                        raise ValueError('non-numeric component')
                out.append(int(chunk))
            return out

        left = parse(a)
        right = parse(b)
        width = max(len(left), len(right))
        for i in range(width):
            x = left[i] if i < len(left) else 0
            y = right[i] if i < len(right) else 0
            if x < y:
                return -1
            if x > y:
                return 1
        return 0
    """,
))

SPECS.append(spec(
    id="hr21",
    title="deep_merge",
    difficulty="hard",
    objective="""
    def deep_merge(base: dict, other: dict) -> dict

    Combine two dictionaries into a new one. Where both hold a dictionary
    under the same key, those dictionaries are merged by the same rule, all
    the way down. Where they disagree in any other way — including when one
    side holds a list and the other a dictionary — the value from `other`
    replaces the value from `base` outright. Lists are never concatenated or
    merged element-wise.

    Both arguments are read-only, and the result must share no mutable object
    with either of them: changing something nested inside the result must
    leave both inputs exactly as they were.
    """,
    holdout_test="""
    a = {'x': 1, 'n': {'p': 1, 'q': 2}, 'l': [1, 2]}
    b = {'n': {'q': 3, 'r': 4}, 'l': [9], 'y': 5}
    r = deep_merge(a, b)
    assert r == {'x': 1, 'n': {'p': 1, 'q': 3, 'r': 4}, 'l': [9], 'y': 5}
    assert a == {'x': 1, 'n': {'p': 1, 'q': 2}, 'l': [1, 2]}
    assert b == {'n': {'q': 3, 'r': 4}, 'l': [9], 'y': 5}
    r['n']['p'] = 99
    assert a['n']['p'] == 1
    assert deep_merge({}, {}) == {}
    assert deep_merge({'a': {'b': 1}}, {'a': 2}) == {'a': 2}
    assert deep_merge({'a': 2}, {'a': {'b': 1}}) == {'a': {'b': 1}}
    assert deep_merge({'a': 1}, {}) == {'a': 1}
    assert deep_merge({}, {'a': 1}) == {'a': 1}
    assert deep_merge({'a': {'b': {'c': 1}}}, {'a': {'b': {'d': 2}}}) == {
        'a': {'b': {'c': 1, 'd': 2}}}
    _src = {'k': {'z': 1}}
    _out = deep_merge(_src, {})
    _out['k']['z'] = 7
    assert _src['k']['z'] == 1
    _lists = {'l': [1, 2]}
    _out3 = deep_merge(_lists, {})
    _out3['l'].append(3)
    assert _lists['l'] == [1, 2]
    _other = {'k': {'z': 3}}
    _out2 = deep_merge({}, _other)
    _out2['k']['z'] = 8
    assert _other['k']['z'] == 3
    print('ok')
    """,
    reference="""
    def deep_merge(base, other):
        def clone(value):
            if isinstance(value, dict):
                return {k: clone(v) for k, v in value.items()}
            if isinstance(value, list):
                return [clone(v) for v in value]
            return value

        out = clone(base)
        for key, value in other.items():
            if isinstance(out.get(key), dict) and isinstance(value, dict):
                out[key] = deep_merge(out[key], value)
            else:
                out[key] = clone(value)
        return out
    """,
))

SPECS.append(spec(
    id="hr22",
    title="flatten_keys",
    difficulty="medium",
    objective="""
    def flatten_keys(d: dict, sep: str = '.') -> dict

    Collapse a dictionary of dictionaries into a single level, where each key
    is the path that reached the value, joined with sep. Values that are not
    dictionaries are carried across unchanged, including lists, even when a
    list contains dictionaries — only dictionaries nested directly under a key
    are descended into.

    A nested dictionary with nothing in it has no paths beneath it, so it is
    kept as a value under its own path. d must not be modified.
    """,
    holdout_test="""
    assert flatten_keys({}) == {}
    assert flatten_keys({'a': 1}) == {'a': 1}
    assert flatten_keys({'a': {'b': {'c': 1}}}) == {'a.b.c': 1}
    assert flatten_keys({'a': {}}) == {'a': {}}
    assert flatten_keys({'a': {'b': 1}, 'c': 2}) == {'a.b': 1, 'c': 2}
    assert flatten_keys({'a': {'b': 1}}, '/') == {'a/b': 1}
    assert flatten_keys({'a': {'b': {}}}) == {'a.b': {}}
    assert flatten_keys({'a': {'b': [1, {'c': 2}]}}) == {'a.b': [1, {'c': 2}]}
    assert flatten_keys({'a': {'b': 1, 'c': {'d': 2}}}) == {'a.b': 1, 'a.c.d': 2}
    assert flatten_keys({'a': None}) == {'a': None}
    _d = {'a': {'b': 1}}
    flatten_keys(_d)
    assert _d == {'a': {'b': 1}}
    print('ok')
    """,
    reference="""
    def flatten_keys(d, sep='.'):
        out = {}
        for key, value in d.items():
            if isinstance(value, dict) and value:
                for sub, item in flatten_keys(value, sep).items():
                    out[str(key) + sep + str(sub)] = item
            else:
                out[key] = value
        return out
    """,
))

SPECS.append(spec(
    id="hr23",
    title="moving_average",
    difficulty="medium",
    objective="""
    def moving_average(values: list, window: int) -> list

    Return the mean of every run of `window` consecutive values, in order, as
    a list of floats. There is one result per position the window can occupy,
    so a window as wide as the input produces a single number and a window
    wider than the input produces none at all.

    Results must be accurate to within 1e-9 of the true mean. A window that is
    not a positive integer describes no run of values and must raise
    ValueError. values must not be modified.
    """,
    holdout_test="""
    assert moving_average([], 1) == []
    assert moving_average([1, 2, 3], 5) == []
    assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]
    assert moving_average([1, 2, 3], 3) == [2.0]
    assert moving_average([1, 2, 3], 1) == [1.0, 2.0, 3.0]
    assert moving_average([-1, 1, -1, 1], 2) == [0.0, 0.0, 0.0]
    assert moving_average([5, 5, 5, 5], 4) == [5.0]
    _r = moving_average([0.1, 0.2, 0.3], 2)
    assert len(_r) == 2
    assert abs(_r[0] - 0.15) < 1e-9
    assert abs(_r[1] - 0.25) < 1e-9
    _rejected = []
    for _w in [0, -1]:
        try:
            moving_average([1, 2], _w)
        except ValueError:
            _rejected.append(_w)
    assert _rejected == [0, -1]
    _v = [1, 2, 3]
    moving_average(_v, 2)
    assert _v == [1, 2, 3]
    print('ok')
    """,
    reference="""
    def moving_average(values, window):
        if not isinstance(window, int) or window < 1:
            raise ValueError('window must be a positive integer')
        out = []
        for start in range(len(values) - window + 1):
            chunk = values[start:start + window]
            out.append(sum(chunk) / window)
        return out
    """,
))

SPECS.append(spec(
    id="hr24",
    title="run_length_decode",
    difficulty="medium",
    objective="""
    def run_length_decode(s: str) -> str

    Expand a run-length encoded string. The encoding alternates: one character
    of data, then a decimal repeat count of one or more digits saying how many
    times that character occurs. Data characters are never digits, and a
    repeat count is never zero. Whitespace is ordinary data. Decoding nothing
    yields nothing.

    Anything that does not follow that shape — a data character with no count,
    a count where a data character was expected, or a count of zero — must
    raise ValueError.
    """,
    holdout_test="""
    assert run_length_decode('') == ''
    assert run_length_decode('a1') == 'a'
    assert run_length_decode('a3b2') == 'aaabb'
    assert run_length_decode('a12') == 'aaaaaaaaaaaa'
    assert run_length_decode('x1y1z1') == 'xyz'
    assert run_length_decode(' 2') == '  '
    assert run_length_decode('a10b1') == 'aaaaaaaaaab'
    assert run_length_decode('-3') == '---'
    _bad = 0
    for _s in ['a', '3a', 'a0', 'ab2', 'a2b', '1', '31']:
        try:
            run_length_decode(_s)
        except ValueError:
            _bad += 1
    assert _bad == 7
    print('ok')
    """,
    reference="""
    def run_length_decode(s):
        out = []
        i = 0
        while i < len(s):
            ch = s[i]
            if ch in '0123456789':
                raise ValueError('expected a data character')
            j = i + 1
            while j < len(s) and s[j] in '0123456789':
                j += 1
            count = int(s[i + 1:j])
            if count < 1:
                raise ValueError('repeat count must be at least one')
            out.append(ch * count)
            i = j
        return ''.join(out)
    """,
))

SPECS.append(spec(
    id="hr25",
    title="next_permutation",
    difficulty="hard",
    objective="""
    def next_permutation(seq: list) -> list

    Return a new list holding the next permutation of seq in lexicographic
    order — the smallest rearrangement of the same elements that is strictly
    greater than seq. When seq is already the greatest such arrangement, the
    ordering wraps around and the smallest one is returned instead.

    Repeated elements are handled like any others. seq must not be modified,
    and the returned list must be independent of it. A list too short to have
    a next permutation comes back unchanged in value.
    """,
    holdout_test="""
    assert next_permutation([1, 2, 3]) == [1, 3, 2]
    assert next_permutation([1, 3, 2]) == [2, 1, 3]
    assert next_permutation([2, 3, 1]) == [3, 1, 2]
    assert next_permutation([3, 2, 1]) == [1, 2, 3]
    assert next_permutation([1, 1, 5]) == [1, 5, 1]
    assert next_permutation([1, 5, 1]) == [5, 1, 1]
    assert next_permutation([5, 1, 1]) == [1, 1, 5]
    assert next_permutation([]) == []
    assert next_permutation([1]) == [1]
    assert next_permutation([1, 2]) == [2, 1]
    assert next_permutation([2, 1]) == [1, 2]
    _s = [1, 2, 3]
    _out = next_permutation(_s)
    assert _s == [1, 2, 3]
    _out.append(0)
    assert _s == [1, 2, 3]
    print('ok')
    """,
    reference="""
    def next_permutation(seq):
        out = list(seq)
        i = len(out) - 2
        while i >= 0 and out[i] >= out[i + 1]:
            i -= 1
        if i >= 0:
            j = len(out) - 1
            while out[j] <= out[i]:
                j -= 1
            out[i], out[j] = out[j], out[i]
        out[i + 1:] = reversed(out[i + 1:])
        return out
    """,
))

SPECS.append(spec(
    id="hr26",
    title="luhn_check",
    difficulty="medium",
    objective="""
    def luhn_check(number: str) -> bool

    Decide whether a string of digits satisfies the Luhn checksum. Spaces and
    hyphens may appear anywhere as grouping and are ignored. Working from the
    rightmost digit leftwards, every second digit is doubled, and a doubled
    result of ten or more has nine subtracted from it; the string is valid
    when the resulting digits sum to a multiple of ten.

    A string holding fewer than two digits cannot be a checksummed number, and
    neither can one containing any other character. Both cases are simply
    invalid — return False rather than raising.
    """,
    holdout_test="""
    assert luhn_check('4539 1488 0343 6467') is True
    assert luhn_check('4539-1488-0343-6467') is True
    assert luhn_check('8273 1232 7352 0569') is False
    assert luhn_check('8273123273520569') is False
    assert luhn_check('059') is True
    assert luhn_check('59') is True
    assert luhn_check('109') is True
    assert luhn_check('0 0') is True
    assert luhn_check('  0 0 ') is True
    assert luhn_check('0') is False
    assert luhn_check('1') is False
    assert luhn_check('') is False
    assert luhn_check('123a') is False
    assert luhn_check('9999999999999999') is False
    assert luhn_check('055 444 285') is True
    assert luhn_check('18') is True
    assert luhn_check('26') is True
    assert luhn_check('34') is True
    assert luhn_check('42') is True
    assert luhn_check('67') is True
    assert luhn_check('75') is True
    assert luhn_check('83') is True
    assert luhn_check('91') is True
    print('ok')
    """,
    reference="""
    def luhn_check(number):
        doubled = [0, 2, 4, 6, 8, 1, 3, 5, 7, 9]
        digits = []
        for ch in number:
            if ch in ' -':
                continue
            if ch not in '0123456789':
                return False
            digits.append(int(ch))
        if len(digits) < 2:
            return False
        values = []
        for index, digit in enumerate(reversed(digits)):
            if index % 2 == 1:
                values.append(doubled[digit])
            else:
                values.append(digit)
        return sum(values) % 10 == 0
    """,
))

SPECS.append(spec(
    id="hr27",
    title="parse_duration",
    difficulty="medium",
    objective="""
    def parse_duration(s: str) -> int

    Read a compact duration such as a count of days, hours, minutes and
    seconds written as digits each followed by one of the unit letters
    d, h, m, s, and return the total number of seconds. A unit may be omitted,
    but the units that do appear must be in descending order of size and none
    may appear twice.

    The whole string must be consumed by that pattern and at least one unit
    must be present. Anything else — an empty string, a stray character, a
    space between the parts, a fractional number, a unit with no number, or a
    number with no unit — must raise ValueError.
    """,
    holdout_test="""
    assert parse_duration('45s') == 45
    assert parse_duration('0s') == 0
    assert parse_duration('90m') == 5400
    assert parse_duration('1h30m') == 5400
    assert parse_duration('10h') == 36000
    assert parse_duration('2d') == 172800
    assert parse_duration('1d2h3m4s') == 93784
    assert parse_duration('1d4s') == 86404
    _bad = 0
    for _s in ['', 's', '1x', '30m1h', '1h1h', '1h 30m', '1.5h', '10', 'd']:
        try:
            parse_duration(_s)
        except ValueError:
            _bad += 1
    assert _bad == 9
    print('ok')
    """,
    reference="""
    def parse_duration(s):
        units = [('d', 86400), ('h', 3600), ('m', 60), ('s', 1)]
        total = 0
        pos = 0
        matched = 0
        for symbol, seconds in units:
            start = pos
            while pos < len(s) and s[pos] in '0123456789':
                pos += 1
            if pos == start:
                continue
            if pos >= len(s) or s[pos] != symbol:
                pos = start
                continue
            total += int(s[start:pos]) * seconds
            pos += 1
            matched += 1
        if matched < 1 or pos != len(s):
            raise ValueError('malformed duration')
        return total
    """,
))

SPECS.append(spec(
    id="hr28",
    title="parse_csv_line",
    difficulty="hard",
    objective="""
    def parse_csv_line(line: str) -> list

    Split one line of CSV into its fields. Fields are separated by commas. A
    field may instead be wrapped in double quotes, and inside those quotes a
    comma is ordinary text and a pair of double quotes stands for one literal
    double quote character.

    An unquoted field is taken exactly as written, spaces included; a field
    with nothing in it is the empty string. A line that is itself empty still
    holds one (empty) field.

    A quoted field that is never closed, or that has text between its closing
    quote and the next separator, is malformed and must raise ValueError.
    """,
    holdout_test="""
    assert parse_csv_line('') == ['']
    assert parse_csv_line('a,b,c') == ['a', 'b', 'c']
    assert parse_csv_line('a,,c') == ['a', '', 'c']
    assert parse_csv_line('"a,b",c') == ['a,b', 'c']
    assert parse_csv_line('"a""b"') == ['a"b']
    assert parse_csv_line(' a , b ') == [' a ', ' b ']
    assert parse_csv_line('a,') == ['a', '']
    assert parse_csv_line(',') == ['', '']
    assert parse_csv_line('""') == ['']
    assert parse_csv_line('"",""') == ['', '']
    assert parse_csv_line('x,"y"') == ['x', 'y']
    assert parse_csv_line('"a"",b"') == ['a",b']
    _bad = 0
    for _s in ['"abc', '"a"b', '"a,b', 'a,"b']:
        try:
            parse_csv_line(_s)
        except ValueError:
            _bad += 1
    assert _bad == 4
    print('ok')
    """,
    reference="""
    def parse_csv_line(line):
        fields = []
        i = 0
        n = len(line)
        while True:
            if i < n and line[i] == '"':
                i += 1
                chars = []
                while True:
                    if i >= n:
                        raise ValueError('unterminated quoted field')
                    if line[i] == '"':
                        if i + 1 < n and line[i + 1] == '"':
                            chars.append('"')
                            i += 2
                            continue
                        i += 1
                        break
                    chars.append(line[i])
                    i += 1
                if i < n and line[i] != ',':
                    raise ValueError('text after a closing quote')
                fields.append(''.join(chars))
            else:
                start = i
                while i < n and line[i] != ',':
                    i += 1
                fields.append(line[start:i])
            if i >= n:
                return fields
            i += 1
    """,
))

SPECS.append(spec(
    id="hr29",
    title="humanize_bytes",
    difficulty="medium",
    objective="""
    def humanize_bytes(n: int) -> str

    Render a byte count for a human reader, using the units B, KB, MB, GB, TB
    and PB where each is 1024 of the one before. Pick the largest unit that
    leaves a value of at least one, before any rounding; petabytes are the
    largest unit available, so very large counts stay in petabytes however big
    the number in front becomes.

    A count in plain bytes is written as a whole number; every other unit is
    written with exactly one digit after the decimal point. The number and the
    unit are separated by a single space. A negative count is not a size and
    must raise ValueError.
    """,
    holdout_test="""
    assert humanize_bytes(0) == '0 B'
    assert humanize_bytes(1) == '1 B'
    assert humanize_bytes(1023) == '1023 B'
    assert humanize_bytes(1024) == '1.0 KB'
    assert humanize_bytes(1536) == '1.5 KB'
    assert humanize_bytes(1048575) == '1024.0 KB'
    assert humanize_bytes(1048576) == '1.0 MB'
    assert humanize_bytes(1073741824) == '1.0 GB'
    assert humanize_bytes(1099511627776) == '1.0 TB'
    assert humanize_bytes(1125899906842624) == '1.0 PB'
    assert humanize_bytes(1152921504606846976) == '1024.0 PB'
    assert humanize_bytes(2048) == '2.0 KB'
    _err = None
    try:
        humanize_bytes(-1)
    except ValueError:
        _err = 'ValueError'
    assert _err == 'ValueError'
    print('ok')
    """,
    reference="""
    def humanize_bytes(n):
        if n < 0:
            raise ValueError('a byte count is not negative')
        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
        index = 0
        value = float(n)
        while value >= 1024 and index < len(units) - 1:
            value = value / 1024
            index += 1
        if index == 0:
            return str(int(value)) + ' B'
        return '{:.1f} {}'.format(value, units[index])
    """,
))

SPECS.append(spec(
    id="hr30",
    title="max_subarray_sum",
    difficulty="medium",
    objective="""
    def max_subarray_sum(nums: list) -> int

    Return the largest sum obtainable from a contiguous, non-empty run of
    values in nums. The run may be the whole list or a single element, but it
    may not be empty — so a list of nothing but negative numbers still has an
    answer, and it is not zero.

    A list with no elements has no non-empty run at all and must raise
    ValueError. nums must not be modified.
    """,
    holdout_test="""
    assert max_subarray_sum([1]) == 1
    assert max_subarray_sum([-1]) == -1
    assert max_subarray_sum([-2, -3, -1, -5]) == -1
    assert max_subarray_sum([-2, 1, -3, 4, -1, 2, 1, -5, 4]) == 6
    assert max_subarray_sum([5, -1, 5]) == 9
    assert max_subarray_sum([0, -1]) == 0
    assert max_subarray_sum([-1, 0]) == 0
    assert max_subarray_sum([2, -1, 2, -1, 2]) == 4
    assert max_subarray_sum([1, 2, 3]) == 6
    assert max_subarray_sum([-5, -2, -9]) == -2
    _err = None
    try:
        max_subarray_sum([])
    except ValueError:
        _err = 'ValueError'
    assert _err == 'ValueError'
    _v = [1, -2, 3]
    max_subarray_sum(_v)
    assert _v == [1, -2, 3]
    print('ok')
    """,
    reference="""
    def max_subarray_sum(nums):
        if not nums:
            raise ValueError('no non-empty run exists')
        best = nums[0]
        current = nums[0]
        for value in nums[1:]:
            current = max(value, current + value)
            best = max(best, current)
        return best
    """,
))

SPECS.append(spec(
    id="hr31",
    title="trapped_water",
    difficulty="hard",
    objective="""
    def trapped_water(heights: list) -> int

    heights gives the height of each bar in a row of bars one unit wide.
    After rain, water settles in the dips: above each position the water
    stands as high as the lower of the tallest bar to its left and the tallest
    bar to its right, minus the bar itself, and never below zero. Return the
    total units of water held.

    A row that only rises, or only falls, holds nothing, and neither does an
    empty row. heights must not be modified.
    """,
    holdout_test="""
    assert trapped_water([]) == 0
    assert trapped_water([1]) == 0
    assert trapped_water([1, 2]) == 0
    assert trapped_water([3, 2, 1]) == 0
    assert trapped_water([1, 2, 3]) == 0
    assert trapped_water([5, 0, 5]) == 5
    assert trapped_water([2, 0, 2, 0, 2]) == 4
    assert trapped_water([0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1]) == 6
    assert trapped_water([4, 2, 0, 3, 2, 5]) == 9
    assert trapped_water([0, 0, 0]) == 0
    assert trapped_water([3, 1, 2]) == 1
    _h = [3, 0, 3]
    trapped_water(_h)
    assert _h == [3, 0, 3]
    print('ok')
    """,
    reference="""
    def trapped_water(heights):
        if not heights:
            return 0
        left = 0
        right = len(heights) - 1
        left_max = heights[left]
        right_max = heights[right]
        total = 0
        while left < right:
            if left_max <= right_max:
                left += 1
                left_max = max(left_max, heights[left])
                total += left_max - heights[left]
            else:
                right -= 1
                right_max = max(right_max, heights[right])
                total += right_max - heights[right]
        return total
    """,
))

SPECS.append(spec(
    id="hr32",
    title="lis_length",
    difficulty="medium",
    objective="""
    def lis_length(nums: list) -> int

    Return the length of the longest strictly increasing subsequence of nums.
    The chosen values keep their original relative order but need not be
    adjacent, and each must be strictly greater than the one before it, so
    equal values can never both be chosen.

    An empty list has no subsequence and answers zero. nums must not be
    modified.
    """,
    holdout_test="""
    assert lis_length([]) == 0
    assert lis_length([7]) == 1
    assert lis_length([3, 2, 1]) == 1
    assert lis_length([7, 7, 7, 7]) == 1
    assert lis_length([1, 2, 3, 4]) == 4
    assert lis_length([10, 9, 2, 5, 3, 7, 101, 18]) == 4
    assert lis_length([0, 1, 0, 3, 2, 3]) == 4
    assert lis_length([2, 2, 3, 1, 4]) == 3
    assert lis_length([1, 3, 2]) == 2
    assert lis_length([-5, -1, 0]) == 3
    _n = [1, 3, 2]
    lis_length(_n)
    assert _n == [1, 3, 2]
    print('ok')
    """,
    reference="""
    def lis_length(nums):
        best = []
        for i in range(len(nums)):
            longest = 1
            for j in range(i):
                if nums[j] < nums[i]:
                    longest = max(longest, best[j] + 1)
            best.append(longest)
        if not best:
            return 0
        return max(best)
    """,
))

SPECS.append(spec(
    id="hr33",
    title="can_segment",
    difficulty="hard",
    objective="""
    def can_segment(text: str, words: list) -> bool

    Decide whether text can be written as a sequence of entries from words,
    laid end to end with nothing left over. An entry may be used as often as
    it is needed, or not at all, and the entries need not be used in the order
    given.

    Text with nothing in it is already segmented and answers True. Note that
    always taking the longest entry that fits at each step can fail on inputs
    that do have a segmentation.
    """,
    holdout_test="""
    assert can_segment('', ['a']) is True
    assert can_segment('', []) is True
    assert can_segment('a', ['a']) is True
    assert can_segment('abc', []) is False
    assert can_segment('leetcode', ['leet', 'code']) is True
    assert can_segment('applepenapple', ['apple', 'pen']) is True
    assert can_segment('catsandog', ['cats', 'dog', 'sand', 'and', 'cat']) is False
    assert can_segment('aaaaaaa', ['aaa', 'aaaa']) is True
    assert can_segment('aaab', ['a', 'aa']) is False
    assert can_segment('cars', ['car', 'ca', 'rs']) is True
    assert can_segment('ab', ['a']) is False
    print('ok')
    """,
    reference="""
    def can_segment(text, words):
        n = len(text)
        reachable = [True] + [False] * n
        end = 1
        while end <= n:
            for word in words:
                start = end - len(word)
                if start >= 0 and reachable[start] and text[start:end] == word:
                    reachable[end] = True
            end += 1
        return reachable[n]
    """,
))

SPECS.append(spec(
    id="hr34",
    title="topo_order",
    difficulty="hard",
    objective="""
    def topo_order(graph: dict) -> list

    graph maps a node to the list of nodes that must come before it. Return an
    ordering of every node involved — those that appear as keys and those that
    appear only as prerequisites — in which no node is listed before something
    it depends on.

    Several orderings usually satisfy that, so the answer is pinned down:
    whenever more than one node is available, the smallest available node is
    taken next. Dependencies that cannot all be satisfied, including a node
    that depends on itself, must raise ValueError. graph must not be modified.
    """,
    holdout_test="""
    assert topo_order({}) == []
    assert topo_order({'a': []}) == ['a']
    assert topo_order({'b': ['a']}) == ['a', 'b']
    assert topo_order({'b': [], 'a': []}) == ['a', 'b']
    assert topo_order({'c': ['a', 'b'], 'b': ['a'], 'a': []}) == ['a', 'b', 'c']
    assert topo_order({'d': ['b'], 'c': ['a'], 'b': [], 'a': []}) == ['a', 'b', 'c', 'd']
    assert topo_order({'z': ['y'], 'y': ['x']}) == ['x', 'y', 'z']
    assert topo_order({'b': ['a'], 'c': ['a']}) == ['a', 'b', 'c']
    _bad = 0
    for _g in [{'a': ['b'], 'b': ['a']}, {'a': ['a']}, {'a': ['b'], 'b': ['c'], 'c': ['a']}]:
        try:
            topo_order(_g)
        except ValueError:
            _bad += 1
    assert _bad == 3
    _g = {'b': ['a']}
    topo_order(_g)
    assert _g == {'b': ['a']}
    print('ok')
    """,
    reference="""
    def topo_order(graph):
        nodes = []
        for node in graph:
            if node not in nodes:
                nodes.append(node)
        for deps in graph.values():
            for dep in deps:
                if dep not in nodes:
                    nodes.append(dep)
        remaining = {}
        for node in nodes:
            remaining[node] = list(graph.get(node, []))
        out = []
        while remaining:
            ready = []
            for node in remaining:
                if not remaining[node]:
                    ready.append(node)
            chosen = min(ready)
            out.append(chosen)
            del remaining[chosen]
            for node in remaining:
                if chosen in remaining[node]:
                    remaining[node].remove(chosen)
        return out
    """,
))

SPECS.append(spec(
    id="hr35",
    title="shortest_path",
    difficulty="hard",
    objective="""
    def shortest_path(graph: dict, start, goal) -> tuple

    graph maps each node to a dict of its outgoing neighbours and the
    non-negative cost of reaching them; edges are one-way. Return a tuple of
    the total cost of the cheapest route from start to goal and the list of
    nodes along it, beginning with start and ending with goal.

    Return None when no route exists, and also when either endpoint is not a
    node of the graph. A route from a node to itself costs nothing. When two
    routes cost the same, return whichever list of nodes is smaller in
    ordinary list comparison. graph must not be modified.
    """,
    holdout_test="""
    g = {'a': {'b': 1, 'c': 4}, 'b': {'c': 2, 'd': 5}, 'c': {'d': 1}, 'd': {}}
    assert shortest_path(g, 'a', 'd') == (4, ['a', 'b', 'c', 'd'])
    assert shortest_path(g, 'b', 'd') == (3, ['b', 'c', 'd'])
    assert shortest_path(g, 'a', 'a') == (0, ['a'])
    assert shortest_path(g, 'd', 'a') is None
    assert shortest_path(g, 'a', 'z') is None
    assert shortest_path(g, 'z', 'a') is None
    assert shortest_path({'a': {}}, 'a', 'a') == (0, ['a'])
    assert shortest_path({'a': {'b': 0}, 'b': {}}, 'a', 'b') == (0, ['a', 'b'])
    h = {'a': {'b': 1, 'c': 1}, 'b': {'d': 1}, 'c': {'d': 1}, 'd': {}}
    assert shortest_path(h, 'a', 'd') == (2, ['a', 'b', 'd'])
    assert shortest_path(g, 'a', 'c') == (3, ['a', 'b', 'c'])
    assert g == {'a': {'b': 1, 'c': 4}, 'b': {'c': 2, 'd': 5}, 'c': {'d': 1}, 'd': {}}
    print('ok')
    """,
    reference="""
    def shortest_path(graph, start, goal):
        if start not in graph or goal not in graph:
            return None
        best = {start: (0, [start])}
        visited = set()
        while True:
            current = None
            for node in best:
                if node in visited:
                    continue
                if current is None or best[node] < best[current]:
                    current = node
            if current is None:
                return None
            if current == goal:
                return (best[goal][0], list(best[goal][1]))
            visited.add(current)
            cost, path = best[current]
            for neighbour, weight in graph.get(current, {}).items():
                candidate = (cost + weight, path + [neighbour])
                if neighbour not in best or candidate < best[neighbour]:
                    best[neighbour] = candidate
    """,
))

SPECS.append(spec(
    id="hr36",
    title="count_islands",
    difficulty="medium",
    objective="""
    def count_islands(grid: list) -> int

    grid is a rectangular grid of 0s and 1s. Count the islands: a group of 1s
    that can be walked between by steps up, down, left or right. Cells that
    only touch at a corner belong to different islands.

    A grid of all water, or no grid at all, holds no islands. grid must not be
    modified — in particular it may not be used as scratch space to mark
    cells already visited.
    """,
    holdout_test="""
    assert count_islands([]) == 0
    assert count_islands([[0, 0], [0, 0]]) == 0
    assert count_islands([[1]]) == 1
    assert count_islands([[1, 1], [1, 1]]) == 1
    assert count_islands([[1, 0], [0, 1]]) == 2
    assert count_islands([[1, 0, 1, 0, 1]]) == 3
    assert count_islands([[1], [0], [1]]) == 2
    assert count_islands([[1, 1, 0, 0], [1, 0, 0, 1], [0, 0, 1, 1]]) == 2
    assert count_islands([[1, 1, 1], [0, 1, 0], [1, 1, 1]]) == 1
    _g = [[1, 0], [0, 1]]
    count_islands(_g)
    assert _g == [[1, 0], [0, 1]]
    _h = [[1, 1], [1, 1]]
    count_islands(_h)
    assert _h == [[1, 1], [1, 1]]
    print('ok')
    """,
    reference="""
    def count_islands(grid):
        if not grid:
            return 0
        rows = len(grid)
        cols = len(grid[0])
        seen = set()
        count = 0
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] != 1 or (r, c) in seen:
                    continue
                count += 1
                seen.add((r, c))
                stack = [(r, c)]
                while stack:
                    y, x = stack.pop()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny = y + dy
                        nx = x + dx
                        if ny < 0 or ny >= rows or nx < 0 or nx >= cols:
                            continue
                        if grid[ny][nx] == 1 and (ny, nx) not in seen:
                            seen.add((ny, nx))
                            stack.append((ny, nx))
        return count
    """,
))

SPECS.append(spec(
    id="hr37",
    title="rank_scores",
    difficulty="medium",
    objective="""
    def rank_scores(entries: list) -> list

    entries is a list of (name, score) pairs. Return a list of (name, rank)
    pairs ordered from the highest score down, with names that share a score
    ordered alphabetically between themselves.

    Ranking is competition style: everyone on the same score gets the same
    rank, and the ranks that they collectively use up are skipped, so the next
    lower score resumes at the position it actually occupies rather than the
    next whole number. entries must not be modified.
    """,
    holdout_test="""
    assert rank_scores([]) == []
    assert rank_scores([('a', 5)]) == [('a', 1)]
    assert rank_scores([('a', 5), ('b', 7)]) == [('b', 1), ('a', 2)]
    assert rank_scores([('a', 5), ('b', 5)]) == [('a', 1), ('b', 1)]
    assert rank_scores([('b', 5), ('a', 5), ('c', 5)]) == [('a', 1), ('b', 1), ('c', 1)]
    assert rank_scores([('c', 9), ('a', 5), ('b', 5), ('d', 1)]) == [
        ('c', 1), ('a', 2), ('b', 2), ('d', 4)]
    assert rank_scores([('a', 3), ('b', 3), ('c', 2)]) == [('a', 1), ('b', 1), ('c', 3)]
    assert rank_scores([('a', -1), ('b', 0)]) == [('b', 1), ('a', 2)]
    assert rank_scores([('a', 1), ('b', 2), ('c', 3)]) == [('c', 1), ('b', 2), ('a', 3)]
    _e = [('a', 1), ('b', 2)]
    rank_scores(_e)
    assert _e == [('a', 1), ('b', 2)]
    print('ok')
    """,
    reference="""
    def rank_scores(entries):
        ordered = sorted(entries, key=lambda entry: (-entry[1], entry[0]))
        out = []
        for index, entry in enumerate(ordered):
            if index > 0 and entry[1] == ordered[index - 1][1]:
                rank = out[index - 1][1]
            else:
                rank = index + 1
            out.append((entry[0], rank))
        return out
    """,
))

SPECS.append(spec(
    id="hr38",
    title="parse_query",
    difficulty="hard",
    objective="""
    def parse_query(qs: str) -> dict

    Parse a URL query string into a dict mapping each key to the list of
    values given for it, in the order they appeared. Pairs are separated by
    '&' and a key is separated from its value by the first '=' — any later
    '=' belongs to the value. A pair with no '=' at all still contributes its
    key, with an empty value, and so does a key written with a trailing '='.
    Empty pairs contribute nothing.

    In both keys and values, '+' stands for a space and '%' introduces two
    hexadecimal digits naming a character, in either case. An empty query
    string yields an empty dict. A '%' that is not followed by two hexadecimal
    digits must raise ValueError.
    """,
    holdout_test="""
    assert parse_query('') == {}
    assert parse_query('a=1') == {'a': ['1']}
    assert parse_query('a=1&a=2') == {'a': ['1', '2']}
    assert parse_query('a') == {'a': ['']}
    assert parse_query('a=') == {'a': ['']}
    assert parse_query('a=b=c') == {'a': ['b=c']}
    assert parse_query('a+b=c+d') == {'a b': ['c d']}
    assert parse_query('a=%41%2b') == {'a': ['A+']}
    assert parse_query('a=%2F%2f') == {'a': ['//']}
    assert parse_query('&&a=1&&') == {'a': ['1']}
    assert parse_query('%61=1') == {'a': ['1']}
    assert parse_query('a=1&b=2') == {'a': ['1'], 'b': ['2']}
    _bad = 0
    for _s in ['a=%4', 'a=%zz', 'a=%', '%=1']:
        try:
            parse_query(_s)
        except ValueError:
            _bad += 1
    assert _bad == 4
    print('ok')
    """,
    reference="""
    def parse_query(qs):
        def unquote(text):
            out = []
            i = 0
            while i < len(text):
                ch = text[i]
                if ch == '+':
                    out.append(' ')
                    i += 1
                elif ch == '%':
                    hexed = text[i + 1:i + 3]
                    if len(hexed) < 2:
                        raise ValueError('truncated percent escape')
                    for h in hexed:
                        if h not in '0123456789abcdefABCDEF':
                            raise ValueError('bad percent escape')
                    out.append(chr(int(hexed, 16)))
                    i += 3
                else:
                    out.append(ch)
                    i += 1
            return ''.join(out)

        result = {}
        for pair in qs.split('&'):
            if not pair:
                continue
            if '=' in pair:
                raw_key, raw_value = pair.split('=', 1)
            else:
                raw_key = pair
                raw_value = ''
            key = unquote(raw_key)
            value = unquote(raw_value)
            if key not in result:
                result[key] = []
            result[key].append(value)
        return result
    """,
))

SPECS.append(spec(
    id="hr39",
    title="format_table",
    difficulty="hard",
    objective="""
    def format_table(rows: list) -> str

    Lay out rows of strings as a plain-text table. The first row is the
    header. Every column is padded on the right to the width of its widest
    cell, columns are joined by a space, a pipe and a space, and a rule of
    hyphens exactly as wide as the header line would be if it were not
    trimmed is written under the header.

    Rows need not all be the same length; a missing cell counts as empty. No
    line may end in whitespace, the lines are joined with newlines, and the
    result does not end with one. No rows at all yields an empty string. rows
    must not be modified.
    """,
    holdout_test="""
    assert format_table([]) == ''
    assert format_table([['a']]) == 'a\\n-'
    assert format_table([['x'], ['yy']]) == 'x\\n--\\nyy'
    assert format_table([['ab', 'c'], ['d', 'efg']]) == 'ab | c\\n--------\\nd  | efg'
    assert format_table([['a', 'b'], ['c']]) == 'a | b\\n-----\\nc |'
    assert format_table([['h1', 'h2'], ['a', 'b'], ['ccc', 'd']]) == (
        'h1  | h2\\n--------\\na   | b\\nccc | d')
    assert format_table([['a', 'b']]) == 'a | b\\n-----'
    assert not format_table([['ab', 'c'], ['d', 'efg']]).endswith('\\n')
    assert format_table([['a']]).count('\\n') == 1
    _r = [['a', 'b'], ['c', 'd']]
    format_table(_r)
    assert _r == [['a', 'b'], ['c', 'd']]
    print('ok')
    """,
    reference="""
    def format_table(rows):
        if not rows:
            return ''
        span = max(len(row) for row in rows)
        widths = []
        for col in range(span):
            best = 0
            for row in rows:
                cell = row[col] if col < len(row) else ''
                best = max(best, len(cell))
            widths.append(best)
        lines = []
        for index, row in enumerate(rows):
            cells = []
            for col in range(span):
                cell = row[col] if col < len(row) else ''
                cells.append(cell.ljust(widths[col]))
            lines.append(' | '.join(cells).rstrip())
            if index == 0:
                lines.append('-' * (sum(widths) + 3 * (span - 1)))
        return '\\n'.join(lines)
    """,
))

SPECS.append(spec(
    id="hr40",
    title="edit_distance",
    difficulty="medium",
    objective="""
    def edit_distance(a: str, b: str) -> int

    Return the fewest single-character edits that turn a into b, where an edit
    inserts a character, removes one, or replaces one with another. Comparison
    is case-sensitive, so changing the case of a letter is itself a
    replacement.

    Either string may be empty, in which case the answer is the length of the
    other. Neither argument is modified.
    """,
    holdout_test="""
    assert edit_distance('', '') == 0
    assert edit_distance('', 'abc') == 3
    assert edit_distance('abc', '') == 3
    assert edit_distance('abc', 'abc') == 0
    assert edit_distance('a', 'b') == 1
    assert edit_distance('Abc', 'abc') == 1
    assert edit_distance('kitten', 'sitting') == 3
    assert edit_distance('flaw', 'lawn') == 2
    assert edit_distance('sunday', 'saturday') == 3
    assert edit_distance('ab', 'ba') == 2
    assert edit_distance('abc', 'abcd') == 1
    assert edit_distance('abcd', 'abc') == 1
    print('ok')
    """,
    reference="""
    def edit_distance(a, b):
        previous = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            current = [i + 1]
            for j, cb in enumerate(b):
                cost = 0 if ca == cb else 1
                current.append(min(previous[j] + cost, previous[j + 1] + 1, current[j] + 1))
            previous = current
        return previous[len(b)]
    """,
))

# --------------------------------------------------------------------------
# Mutation engine
# --------------------------------------------------------------------------
#
# Mutation scoring answers the one question a pass rate cannot: would this
# holdout have noticed if the answer were subtly wrong? Each mutant is the
# reference with exactly one plausible mistake in it — the mistakes a model
# actually makes. A surviving mutant is a hole in the assertions, so the gate
# is on the holdout, not on the reference.

_BIN_SWAP = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Add,
    ast.FloorDiv: ast.Div,
    ast.Div: ast.FloorDiv,
    ast.Mod: ast.FloorDiv,
}

_CMP_SWAP = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}


def _fix_empty_bodies(tree: ast.AST) -> None:
    """Dropping a statement can empty a block; unparse would then fail."""
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and not block and field == "body":
                if isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                        ast.ClassDef,
                        ast.If,
                        ast.For,
                        ast.While,
                        ast.With,
                        ast.Try,
                    ),
                ):
                    block.append(ast.Pass())


class _Mutation(ast.NodeTransformer):
    """Apply the `index`-th mutation of kind `kind`, and no other."""

    def __init__(self, kind: str, index: int) -> None:
        self.kind = kind
        self.index = index
        self.seen = 0
        self.applied = False

    def _hit(self) -> bool:
        hit = self.seen == self.index
        self.seen += 1
        if hit:
            self.applied = True
        return hit

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if self.kind == "binop" and type(node.op) in _BIN_SWAP and self._hit():
            node.op = _BIN_SWAP[type(node.op)]()
        return node

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if (
            self.kind == "compare"
            and len(node.ops) == 1
            and type(node.ops[0]) in _CMP_SWAP
            and self._hit()
        ):
            node.ops = [_CMP_SWAP[type(node.ops[0])]()]
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        if self.kind == "boolop" and self._hit():
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        if self.kind == "drop_not" and isinstance(node.op, ast.Not) and self._hit():
            return node.operand
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, bool):
            if self.kind == "flip_bool" and self._hit():
                return ast.Constant(value=not node.value)
            return node
        if isinstance(node.value, int) and abs(node.value) < 10**6:
            if self.kind == "const_inc" and self._hit():
                return ast.Constant(value=node.value + 1)
            if self.kind == "const_dec" and self._hit():
                return ast.Constant(value=node.value - 1)
        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)
        # Constant indices are already covered by const_inc / const_dec.
        if (
            self.kind in ("index_inc", "index_dec")
            and not isinstance(node.slice, (ast.Slice, ast.Constant, ast.Tuple))
            and self._hit()
        ):
            op = ast.Add() if self.kind == "index_inc" else ast.Sub()
            node.slice = ast.BinOp(left=node.slice, op=op, right=ast.Constant(value=1))
        return node

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        self.generic_visit(node)
        if self.kind == "augassign" and type(node.op) in _BIN_SWAP and self._hit():
            node.op = _BIN_SWAP[type(node.op)]()
        return node

    def visit_If(self, node: ast.If) -> Optional[ast.AST]:
        self.generic_visit(node)
        if self.kind == "drop_branch" and self._hit():
            return None
        return node


_STRUCTURAL_KINDS = (
    "binop",
    "compare",
    "boolop",
    "drop_not",
    "const_inc",
    "const_dec",
    "flip_bool",
    "index_inc",
    "index_dec",
    "augassign",
    "drop_branch",
)


def _entry_node(tree: ast.Module, title: str) -> Optional[ast.AST]:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == title:
            return node
    return None


def _replacement_mutants(source: str, title: str) -> List[str]:
    """`return <constant>` / `return <argument>` — the degenerate answers.

    A holdout that these survive is not testing behaviour at all.
    """
    out: List[str] = []
    consts = ["None", "True", "False", "0", "[]", "''"]

    for literal in consts:
        tree = ast.parse(source)
        entry = _entry_node(tree, title)
        if entry is None:
            break
        if isinstance(entry, ast.ClassDef):
            # For a class, gut every method: the invariants go with it.
            changed = False
            for item in entry.body:
                if isinstance(item, ast.FunctionDef) and item.name != "__init__":
                    item.body = ast.parse(f"return {literal}").body
                    changed = True
            if not changed:
                break
        else:
            entry.body = ast.parse(f"return {literal}").body
        out.append(ast.unparse(tree))
        if isinstance(entry, ast.ClassDef):
            break  # one gutting is enough; the rest differ only in literal

    # Identity: return the first real argument untouched.
    tree = ast.parse(source)
    entry = _entry_node(tree, title)
    if isinstance(entry, ast.FunctionDef) and entry.args.args:
        first = entry.args.args[0].arg
        entry.body = ast.parse(f"return {first}").body
        out.append(ast.unparse(tree))
    elif isinstance(entry, ast.ClassDef):
        # Drop each method's body one at a time -> a no-op object.
        for idx, item in enumerate(entry.body):
            if not isinstance(item, ast.FunctionDef):
                continue
            fresh = ast.parse(source)
            target = _entry_node(fresh, title)
            assert isinstance(target, ast.ClassDef)
            method = target.body[idx]
            method.body = ast.parse("return None").body  # type: ignore[union-attr]
            out.append(ast.unparse(fresh))
    return out


def generate_mutants(source: str, title: str, limit: int = MAX_MUTANTS) -> List[str]:
    """Distinct single-edit mutants of `source`, deterministically selected."""
    baseline = ast.unparse(ast.parse(source))

    structural: List[str] = []
    for kind in _STRUCTURAL_KINDS:
        index = 0
        while index < 200:
            tree = ast.parse(source)
            mutation = _Mutation(kind, index)
            tree = mutation.visit(tree)
            if not mutation.applied:
                break
            _fix_empty_bodies(tree)
            ast.fix_missing_locations(tree)
            try:
                text = ast.unparse(tree)
            except Exception:
                index += 1
                continue
            if text != baseline:
                try:
                    compile(text, "<mutant>", "exec")
                except SyntaxError:
                    index += 1
                    continue
                structural.append(text)
            index += 1

    # The degenerate answers always run: they are the cheapest way for a
    # holdout to be caught doing nothing.
    forced = _replacement_mutants(source, title)

    seen = {baseline}
    ordered: List[str] = []
    for text in forced:
        if text not in seen:
            seen.add(text)
            ordered.append(text)

    pool = []
    for text in structural:
        if text not in seen:
            seen.add(text)
            pool.append(text)

    # Deterministic spread across operator families rather than the first N,
    # which would be all `binop`.
    random.Random(title).shuffle(pool)
    room = max(0, limit - len(ordered))
    return ordered + pool[:room]


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------


def existing_names() -> Dict[str, str]:
    """Entry-point names already graded elsewhere -> where they live."""
    names: Dict[str, str] = {}

    try:
        tree = ast.parse(BENCH_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [
                    k.value
                    for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                ]
                if "title" not in keys:
                    continue
                value = node.values[keys.index("title")]
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    names.setdefault(value.value, "scripts/bench.py")
    except Exception:
        pass

    for path, label in ((HOLDOUT_PATH, "holdout_v1.json"), (HUMANEVAL_PATH, "hidden_humaneval.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for task in data.get("tasks") or []:
            title = task.get("title")
            if isinstance(title, str):
                names.setdefault(title, label)
    return names


def static_gates(specs: List[Dict[str, str]]) -> List[str]:
    """Gates 1, 2 and 5 — leakage, prompt hygiene, name collisions."""
    problems: List[str] = []
    blocked = existing_names()
    seen_titles: Dict[str, str] = {}
    seen_ids: Dict[str, str] = {}

    for s in specs:
        tag = f"{s['id']}/{s['title']}"

        if s["difficulty"] not in ("medium", "hard"):
            problems.append(f"{tag}: difficulty must be medium|hard, got {s['difficulty']!r}")

        if s["id"] in seen_ids:
            problems.append(f"{tag}: duplicate id")
        seen_ids[s["id"]] = tag

        if s["title"] in seen_titles:
            problems.append(f"{tag}: duplicate entry-point name (also {seen_titles[s['title']]})")
        seen_titles[s["title"]] = tag

        if s["title"] in blocked:
            problems.append(f"{tag}: name already graded in {blocked[s['title']]}")

        if s["title"] not in s["objective"]:
            problems.append(f"{tag}: objective never names the entry point")

        # Gate 1 — the objective must not contain the answer.
        for issue in check_task_leakage(public_task(s)):
            problems.append(f"{tag}: leakage — {issue}")

        # Gate 2 — same check, from the prompt side.
        verdict = prompt_check(s["objective"], s["holdout_test"])
        if not verdict["clean"]:
            problems.append(f"{tag}: prompt_guard — {verdict['detail']}")

        # A holdout is only as good as the assertions it contributes.
        lines = assertion_lines(s["holdout_test"])
        if len(lines) < MIN_ASSERTS:
            problems.append(f"{tag}: {len(lines)} assertions, need >= {MIN_ASSERTS}")
        real = count_real_asserts(s["holdout_test"])
        if real < MIN_ASSERTS:
            problems.append(f"{tag}: {real} observable assertions, need >= {MIN_ASSERTS}")

        # The reference must parse, and must define what the task asks for.
        try:
            tree = ast.parse(s["reference"])
        except SyntaxError as e:
            problems.append(f"{tag}: reference does not parse: {e}")
            continue
        if _entry_node(tree, s["title"]) is None:
            problems.append(f"{tag}: reference defines no top-level {s['title']}")

        # The reference must never reach the prompt.
        if s["reference"] in s["objective"]:
            problems.append(f"{tag}: reference source appears in the objective")

    return problems


def _grade(code: str, holdout: str, timeout: int) -> bool:
    from core.holdout import grade_against_holdout

    try:
        return bool(grade_against_holdout(code, holdout, timeout=timeout)["ok"])
    except Exception:
        return False


def dynamic_gates(
    specs: List[Dict[str, str]], jobs: int, verbose: bool = True
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Gates 3 and 4 — solvable, and able to tell right from nearly-right."""
    from core.holdout import grade_against_holdout

    problems: List[str] = []
    report: List[Dict[str, Any]] = []

    for s in specs:
        tag = f"{s['id']}/{s['title']}"
        started = time.time()

        # Gate 3 — SOLVABLE. An impossible assertion scores every model wrong.
        verdict = grade_against_holdout(s["reference"], s["holdout_test"], timeout=REF_TIMEOUT)
        if not verdict["ok"]:
            problems.append(
                f"{tag}: reference FAILS its own holdout — {verdict['reason']} "
                f"{verdict.get('stderr', '')[-200:]}"
            )
            report.append({"id": s["id"], "title": s["title"], "solvable": False,
                           "mutants": 0, "killed": 0, "score": 0.0, "survivors": []})
            if verbose:
                print(f"  {tag:<34} UNSOLVABLE — {verdict['reason']}", flush=True)
            continue

        # Gate 4 — DISCRIMINATING.
        mutants = generate_mutants(s["reference"], s["title"])
        if len(mutants) < MIN_MUTANTS:
            problems.append(f"{tag}: only {len(mutants)} mutants, need >= {MIN_MUTANTS}")

        # `holdout` is bound here rather than closed over: `s` is the loop
        # variable, and a lambda that reads it would grade whichever task the
        # loop had reached by the time the pool got round to running.
        holdout = s["holdout_test"]
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            results = list(
                pool.map(lambda m, h=holdout: _grade(m, h, MUTANT_TIMEOUT), mutants)
            )

        survivors = [m for m, ok in zip(mutants, results) if ok]
        killed = len(mutants) - len(survivors)
        score = killed / len(mutants) if mutants else 0.0

        if score < MIN_MUTATION_SCORE:
            problems.append(
                f"{tag}: mutation score {score:.2f} < {MIN_MUTATION_SCORE:.2f} "
                f"({len(survivors)} survivor(s)) — the holdout cannot fail a wrong answer"
            )

        report.append(
            {
                "id": s["id"],
                "title": s["title"],
                "difficulty": s["difficulty"],
                "solvable": True,
                "mutants": len(mutants),
                "killed": killed,
                "score": round(score, 3),
                "survivors": survivors,
            }
        )
        if verbose:
            flag = "" if score >= MIN_MUTATION_SCORE else "  <-- WEAK"
            print(
                f"  {tag:<34} {killed:>2}/{len(mutants):<2} = {score:.2f}"
                f"  ({time.time() - started:.1f}s){flag}",
                flush=True,
            )
    return problems, report


def build_document(specs: List[Dict[str, str]]) -> Dict[str, Any]:
    return {
        "version": "headroom-v1",
        "description": (
            "Held-out benchmark sized for measurable headroom: tasks a bare model "
            "gets right roughly half the time, so an ablation can resolve a real "
            "difference. Objectives carry a signature and prose only; assertions "
            "live in holdout_test and are never shown to the generator. Reference "
            "implementations are deliberately absent — they exist only in "
            "scripts/build_headroom.py, where they are used for mutation scoring."
        ),
        "gates": {
            "leakage": "core.curriculum.check_task_leakage",
            "prompt": "core.prompt_guard.check",
            "solvable": "core.holdout.grade_against_holdout(reference) == ok",
            "discriminating": f"mutation score >= {MIN_MUTATION_SCORE}",
            "min_assertions": MIN_ASSERTS,
            "min_mutants": MIN_MUTANTS,
        },
        "tasks": [public_task(s) for s in specs],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="run every gate, write nothing")
    parser.add_argument("--static-only", action="store_true", help="skip sandbox gates (3, 4)")
    parser.add_argument("--jobs", type=int, default=6, help="parallel sandbox grades")
    parser.add_argument("--only", default="", help="comma-separated ids, for iterating")
    parser.add_argument("--json-report", default="", help="write the mutation report here")
    args = parser.parse_args(argv)

    specs = list(SPECS)
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        specs = [s for s in specs if s["id"] in wanted or s["title"] in wanted]

    print(f"headroom: {len(specs)} tasks")
    problems = static_gates(specs)
    if problems:
        print("\nSTATIC GATES FAILED — nothing written:")
        for p in problems:
            print(f"  - {p}")
        return 2
    print("  static gates (leakage, prompt_guard, names, assertions): clean")

    report: List[Dict[str, Any]] = []
    if not args.static_only:
        print("\ngrading reference + mutants (no LLM is involved):")
        dyn, report = dynamic_gates(specs, jobs=max(1, args.jobs))
        if dyn:
            print("\nDYNAMIC GATES FAILED — nothing written:")
            for p in dyn:
                print(f"  - {p}")
            # Show the surviving edit, not the whole file: the point is which
            # single change the holdout failed to notice.
            import difflib

            by_title = {s["title"]: s["reference"] for s in specs}
            for row in report:
                for survivor in row.get("survivors", []):
                    base = ast.unparse(ast.parse(by_title[row["title"]])).splitlines()
                    diff = [
                        line
                        for line in difflib.unified_diff(
                            base, survivor.splitlines(), lineterm="", n=0
                        )
                        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
                    ]
                    print(f"\n  survived in {row['title']}:")
                    for line in diff:
                        print(f"      {line}")
            return 3
        scores = [r["score"] for r in report]
        print(
            f"\n  mutation score: min {min(scores):.2f}  mean {sum(scores)/len(scores):.3f}"
            f"  over {sum(r['mutants'] for r in report)} mutants"
        )

    if args.json_report and report:
        Path(args.json_report).write_text(
            json.dumps([{k: v for k, v in r.items() if k != "survivors"} for r in report], indent=2),
            encoding="utf-8",
        )

    if args.verify_only:
        print("\n--verify-only: all gates pass, nothing written")
        return 0

    document = build_document(specs)
    blob = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    # Last line of defence. If a reference ever reached the document, the
    # answer would ship with the question.
    for s in specs:
        for line in s["reference"].splitlines():
            body = line.strip()
            if len(body) > 24 and body in blob:
                print(f"\nREFUSING TO WRITE: reference line from {s['title']} is in the output")
                return 4

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(blob, encoding="utf-8")
    print(f"\nwrote {OUT_PATH.relative_to(ROOT)} ({len(document['tasks'])} tasks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
