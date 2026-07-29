#!/usr/bin/env python3
"""Build `memory/quizzes/calibrated_v1.json` — a bench whose difficulty was MEASURED.

WHY THIS EXISTS
---------------
Three benchmarks have now failed to answer whether @ETHER beats the bare model
it runs on. `scripts/bench.py` leaked its own assertions into the prompt through
BM25 retrieval. `memory/quizzes/holdout_v1.json` leaked *and* asked for
`is_even`. `memory/quizzes/headroom_v1.json` fixed the leaks, was built to land
a bare model at 0.4-0.7 — and measured **0.933**. Every arm sat at the ceiling,
3 to 5 tasks disagreed against an exact-McNemar floor of 6 one-sided discordant
pairs, and the experiment could not have detected an effect if one existed.

The difference between 0.4-0.7 and 0.933 is the difference between a prior and
a measurement. `build_headroom.py` gated hard on leakage, solvability and
mutation score — all of which it passed — and then *estimated* the one quantity
the experiment's power actually depends on. It was wrong by about 25 points, and
nothing in the build could have noticed, because nothing in the build ever asked
the model.

So this file asks the model. Difficulty here is a measurement with a stated
sampling error, not an adjective in a `difficulty` field.

THE PIPELINE
------------
  1. ~70 CANDIDATES, deliberately harder than headroom_v1 (see `SPECS`).
  2. The SAME five gates `build_headroom.py` refuses to write without —
     leakage, prompt hygiene, >= 6 observable assertions, the reference passes
     its own holdout, and mutation score >= 0.90 over >= 15 mutants. All
     fail-closed. A candidate that cannot discriminate is dropped BEFORE
     calibration, because model time spent on it is wasted either way.
  3. CALIBRATION. Every surviving candidate is generated three times by the
     BARE model — objective only, one message to `gems.rose_quartz.router`, no
     plan, no retrieval, no repair, no pipeline — at temperature 0.2 with seeds
     1, 2, 3 and `think=false`, and each sample is graded through
     `core.holdout.grade_against_holdout`. That yields a measured bare pass
     rate in {0, 1/3, 2/3, 1}.
  4. SELECTION. Anything the bare model solves on all three seeds is discarded:
     a task at the ceiling contributes no information about a scaffold. The
     final suite is chosen from the rest to land the overall bare rate near
     0.55, which is where a paired test has the most room to resolve a
     difference in either direction.

Every candidate's measured rate — including the rejects — is recorded in
`MEASURED_BARE_RATE` below and shipped in the output document. That table is
the thing this project has never had, and it cost ~200 generations to get.

WHY THE MEASUREMENT IS NOT ITSELF A LEAK
----------------------------------------
Calibration reads the model, it does not write to it: no result is stored in the
experience vault, the curriculum, the bandit or the run ledger, and the
calibration prompt is the objective alone. `MEASURED_BARE_RATE` is a property of
the task, and selecting hard tasks selects on the *baseline*, not on either arm
of a future comparison — the ceiling filter is applied symmetrically before any
arm exists. It does bias the suite: a bare rate measured on the selection sample
is optimistically low when re-measured (regression to the mean over three
Bernoulli draws). The honest reading is in `power_note()`, which reports the
projected discordant-pair count rather than a p-value this file cannot know.

THE REFERENCE NEVER SHIPS
-------------------------
`reference` exists only to test the test — it is the answer, so writing it into
the dataset would put the answer one BM25 hit from the prompt. Task dicts are
assembled field by field in `public_task()`, never by copying the spec and
deleting a key, and `tests/test_calibrated_suite.py` pins that.

Usage:
    python scripts/build_calibrated.py --static-only      # gates 1, 2, 5
    python scripts/build_calibrated.py --verify-only      # every offline gate
    python scripts/build_calibrated.py --calibrate        # ASKS THE MODEL (slow)
    python scripts/build_calibrated.py --calibrate --resume
    python scripts/build_calibrated.py --emit-measured    # literal to paste below
    python scripts/build_calibrated.py                    # gates + select + write

`--calibrate` is the only mode that touches an LLM, it is strictly serial (one
35B shares this GPU), and it checkpoints after every single sample, so a crash
loses at most one generation.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.assert_audit import count_real_asserts  # noqa: E402
from core.curriculum import check_task_leakage  # noqa: E402
from core.dotenv import load_dotenv  # noqa: E402
from core.prompt_guard import assertion_lines, check as prompt_check  # noqa: E402

# The gates and the mutation engine are imported, not re-implemented. Two
# copies of a mutation operator table drift, and the one that drifts is always
# the copy the new suite uses.
from scripts import build_headroom as bh  # noqa: E402

load_dotenv(ROOT / ".env")

OUT_PATH = ROOT / "memory" / "quizzes" / "calibrated_v1.json"
HEADROOM_PATH = ROOT / "memory" / "quizzes" / "headroom_v1.json"
SAMPLES_PATH = ROOT / "memory" / "scratch" / "calibration_v1_samples.jsonl"

PREAMBLE = bh.PREAMBLE

MIN_ASSERTS = bh.MIN_ASSERTS
MIN_MUTANTS = bh.MIN_MUTANTS
MIN_MUTATION_SCORE = bh.MIN_MUTATION_SCORE
REF_TIMEOUT = bh.REF_TIMEOUT
MUTANT_TIMEOUT = bh.MUTANT_TIMEOUT

# Calibration constants. These are the experiment's definition of "bare".
CALIBRATION_SEEDS = (1, 2, 3)
CALIBRATION_TEMPERATURE = 0.2
CALIBRATION_MAX_TOKENS = 4096
CALIBRATION_GRADE_TIMEOUT = 30

# A task the bare model solves on every seed cannot produce a discordant pair
# in the direction that matters, so it is not evidence about a scaffold.
MAX_BARE_RATE = 2.0 / 3.0 + 1e-9
TARGET_SUITE_SIZE = 40

# BANDS. The measured distribution over 78 candidates came out bimodal — 15 at
# 0.000, 5 at 0.333, 12 at 0.667, 46 at 1.000 — and that shape, not the suite,
# is the finding: on this task class this model is mostly either fluent or
# stuck, and the middle where an experiment lives is scarce and cannot be
# aimed at by writing harder prose.
#
# Only the middle band carries statistical signal. A task at 1.000 cannot show
# improvement and a task at 0.000 usually cannot either: if neither arm ever
# passes it, both arms tie and the pair is dropped by Wilcoxon and concordant
# under McNemar. Floor tasks still ship — a scaffold that cracks one is exactly
# the result worth having, and excluding them would bias the suite toward
# problems the bare model half-knows — but they are marked so nobody counts
# them as power.
BAND_CEILING = "ceiling"      # 3/3 — rejected outright
BAND_FLOOR = "floor"          # 0/3 — shipped, power: none
BAND_INFORMATIVE = "middle"   # 1/3 or 2/3 — the only band that generates signal

ALPHA = 0.05
POWER_TRIALS = 1500
POWER_SEED = 20260728
POWER_TARGET = 0.80


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
    """One candidate. `objective` is prompt-side; `reference` never leaves this file."""
    return {
        "id": id,
        "title": title,
        "difficulty": difficulty,
        "objective": PREAMBLE + _t(objective),
        "holdout_test": _t(holdout_test),
        "reference": _t(reference),
    }


def band_of(rate: float) -> str:
    """Which band a measured rate falls in. The suite's whole accounting."""
    if rate >= 1.0:
        return BAND_CEILING
    if rate <= 0.0:
        return BAND_FLOOR
    return BAND_INFORMATIVE


def public_task(s: Dict[str, str], rate: Optional[float] = None) -> Dict[str, Any]:
    """The dataset row, assembled field by field.

    Deliberately NOT a dict comprehension that drops `reference`: a filter is a
    denylist, and a denylist ships the next field someone adds.
    """
    row: Dict[str, Any] = {
        "id": s["id"],
        "title": s["title"],
        "objective": s["objective"],
        "holdout_test": s["holdout_test"],
        "difficulty": s["difficulty"],
    }
    if rate is not None:
        # `bare_passes` is the measurement; `bare_pass_rate` is a convenience.
        # Consumers must band on the integer: 2/3 written as a decimal is
        # larger than two thirds, and comparing the rounded value against a
        # two-thirds threshold has already silently discarded nine informative
        # tasks once in this file's history.
        row["bare_passes"] = round(rate * len(CALIBRATION_SEEDS))
        row["bare_seeds"] = len(CALIBRATION_SEEDS)
        row["bare_pass_rate"] = round(rate, 4)
        row["band"] = band_of(rate)
        # Stated on the task, not left to the reader of a summary table: a
        # floor task in a pass-rate average looks like difficulty, and in a
        # power calculation it looks like a sample. It is neither.
        row["power"] = "none" if band_of(rate) == BAND_FLOOR else "informative"
    return row


# --------------------------------------------------------------------------
# The candidates
# --------------------------------------------------------------------------
#
# Harder than headroom_v1, along the axes that actually separate a competent
# generator from a lucky one: a multi-step algorithm with a non-obvious
# invariant, an exact output format, a stateful object whose operations
# interact, a named exception with a specified message, a boundary convention
# (half-open ranges, stability, tie-breaks) that the obvious code gets wrong,
# and a few problems where the first idea — sliding window, greedy, sort by
# ratio — is subtly incorrect.
#
# No third-party imports. No trivia. Every objective states a signature and
# prose, and stops short of enumerating its own test cases.

SPECS: List[Dict[str, str]] = []

SPECS.append(spec(
    id="cal01",
    title="wildcard_match",
    difficulty="hard",
    objective="""
    def wildcard_match(pattern: str, text: str) -> bool

    Report whether pattern matches the whole of text. In the pattern, '*'
    stands for any run of characters including none at all, '?' stands for
    exactly one character, and a backslash makes the character after it
    literal so that a pattern can ask for a real star or question mark. Every
    other character stands for itself.

    A backslash at the very end of the pattern has nothing to escape and must
    raise ValueError.
    """,
    holdout_test="""
    assert wildcard_match('', '') is True
    assert wildcard_match('', 'a') is False
    assert wildcard_match('*', '') is True
    assert wildcard_match('**', 'abc') is True
    assert wildcard_match('a*b', 'ab') is True
    assert wildcard_match('a*b', 'axxb') is True
    assert wildcard_match('a*b', 'axxbc') is False
    assert wildcard_match('?', '') is False
    assert wildcard_match('a?c', 'abc') is True
    assert wildcard_match('a?c', 'ac') is False
    assert wildcard_match('*a*', 'bab') is True
    assert wildcard_match('*a*', 'bbb') is False
    assert wildcard_match('\\\\*', '*') is True
    assert wildcard_match('\\\\*', 'x') is False
    assert wildcard_match('a\\\\?', 'a?') is True
    assert wildcard_match('a\\\\?', 'ab') is False
    _err = False
    try:
        wildcard_match('a\\\\', 'a')
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def wildcard_match(pattern, text):
        tokens = []
        k = 0
        while k < len(pattern):
            ch = pattern[k]
            if ch == '\\\\':
                if k + 1 >= len(pattern):
                    raise ValueError('dangling escape')
                tokens.append(('lit', pattern[k + 1]))
                k += 2
            elif ch == '*':
                tokens.append(('star', ''))
                k += 1
            elif ch == '?':
                tokens.append(('any', ''))
                k += 1
            else:
                tokens.append(('lit', ch))
                k += 1
        width = len(text)
        row = [False] * (width + 1)
        row[0] = True
        for kind, ch in tokens:
            nxt = [False] * (width + 1)
            for j in range(width + 1):
                if kind == 'star':
                    nxt[j] = row[j] or (j > 0 and nxt[j - 1])
                elif j > 0 and row[j - 1] and (kind == 'any' or text[j - 1] == ch):
                    nxt[j] = True
            row = nxt
        return row[width]
    """,
))

SPECS.append(spec(
    id="cal02",
    title="justify_text",
    difficulty="hard",
    objective="""
    def justify_text(words: list, width: int) -> list

    Lay the words out as fully justified lines of exactly `width` characters,
    packing greedily: a line takes as many words as fit with one space between
    each, and the next word starts a new line.

    On a line with more than one word the leftover space is spread between the
    gaps as evenly as possible, and when it does not divide evenly the wider
    gaps go on the left. The final line, and any line holding a single word,
    is left-aligned with one space between words and padded on the right.

    A width that is not positive, or a word too long to fit on a line, must
    raise ValueError.
    """,
    holdout_test="""
    assert justify_text([], 5) == []
    assert justify_text(['a'], 3) == ['a  ']
    assert justify_text(['ab', 'cd'], 5) == ['ab cd']
    assert justify_text(['This', 'is', 'an'], 16) == ['This is an      ']
    _out = justify_text(['This', 'is', 'an', 'example', 'of', 'text', 'justification.'], 16)
    assert _out == ['This    is    an', 'example  of text', 'justification.  ']
    assert justify_text(['a', 'b', 'c', 'd'], 5) == ['a b c', 'd    ']
    assert justify_text(['aa', 'bb', 'cc', 'dd'], 8) == ['aa bb cc', 'dd      ']
    assert all(len(line) == 7 for line in justify_text(['x', 'yy', 'zzz', 'w'], 7))
    _err = 0
    try:
        justify_text(['abc'], 2)
    except ValueError:
        _err += 1
    try:
        justify_text(['a'], 0)
    except ValueError:
        _err += 1
    assert _err == 2
    """,
    reference="""
    def justify_text(words, width):
        if width <= 0:
            raise ValueError('width must be positive')
        for word in words:
            if len(word) > width:
                raise ValueError('word does not fit')
        lines = []
        current = []
        used = 0
        for word in words:
            if current and used + len(current) + len(word) > width:
                lines.append(current)
                current = []
                used = 0
            current.append(word)
            used += len(word)
        if current:
            lines.append(current)
        out = []
        for index, line in enumerate(lines):
            if index == len(lines) - 1 or len(line) == 1:
                text = ' '.join(line)
                out.append(text + ' ' * (width - len(text)))
                continue
            spare = width - sum(len(w) for w in line)
            gaps = len(line) - 1
            base = spare // gaps
            extra = spare % gaps
            parts = []
            for k, word in enumerate(line[:-1]):
                parts.append(word + ' ' * (base + (1 if k < extra else 0)))
            parts.append(line[-1])
            out.append(''.join(parts))
        return out
    """,
))

SPECS.append(spec(
    id="cal03",
    title="word_wrap",
    difficulty="hard",
    objective="""
    def word_wrap(text: str, width: int) -> list

    Return the lines of text re-wrapped so that no line is longer than width.

    Runs of whitespace inside a paragraph collapse to a single space and no
    line carries leading or trailing spaces. One or more blank lines separate
    paragraphs, and each paragraph in the result is separated from the next by
    exactly one empty line. A word longer than width cannot be wrapped, so it
    is cut into pieces of exactly width characters until the remainder fits.

    A width that is not positive must raise ValueError.
    """,
    holdout_test="""
    assert word_wrap('', 10) == []
    assert word_wrap('   ', 10) == []
    assert word_wrap('hello world', 20) == ['hello world']
    assert word_wrap('hello   world', 5) == ['hello', 'world']
    assert word_wrap('a b c d e', 3) == ['a b', 'c d', 'e']
    assert word_wrap('one\\n\\ntwo', 10) == ['one', '', 'two']
    assert word_wrap('one\\n\\n\\n\\ntwo', 10) == ['one', '', 'two']
    assert word_wrap('abcdefgh', 3) == ['abc', 'def', 'gh']
    assert word_wrap('xy abcdefg', 3) == ['xy', 'abc', 'def', 'g']
    assert word_wrap('ab\\ncd', 5) == ['ab cd']
    _err = False
    try:
        word_wrap('a', 0)
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def word_wrap(text, width):
        if width <= 0:
            raise ValueError('width must be positive')
        paragraphs = []
        current = []
        for line in text.splitlines():
            if line.strip():
                current.extend(line.split())
            elif current:
                paragraphs.append(current)
                current = []
        if current:
            paragraphs.append(current)
        out = []
        for index, words in enumerate(paragraphs):
            if index:
                out.append('')
            line = ''
            for word in words:
                while len(word) > width:
                    if line:
                        out.append(line)
                        line = ''
                    out.append(word[:width])
                    word = word[width:]
                if not line:
                    line = word
                elif len(line) + 1 + len(word) <= width:
                    line = line + ' ' + word
                else:
                    out.append(line)
                    line = word
            if line:
                out.append(line)
        return out
    """,
))

SPECS.append(spec(
    id="cal04",
    title="IntervalMap",
    difficulty="hard",
    objective="""
    class IntervalMap

    A mapping from integer positions to values, stored as ranges rather than
    points. Support:

      set(lo, hi, value) — assign value to every position in the half-open
      range lo (included) to hi (excluded), replacing whatever was there. An
      empty range changes nothing; lo greater than hi raises ValueError.

      get(x) — the value covering position x, or None where nothing has been
      assigned.

      items() — the assigned ranges as a list of (lo, hi, value) tuples in
      increasing order of lo. Ranges that touch and carry equal values are
      reported as one range, and unassigned gaps are not reported at all.
    """,
    holdout_test="""
    m = IntervalMap()
    assert m.items() == []
    assert m.get(0) is None
    m.set(0, 10, 'a')
    assert m.get(0) == 'a'
    assert m.get(9) == 'a'
    assert m.get(10) is None
    m.set(4, 6, 'b')
    assert m.items() == [(0, 4, 'a'), (4, 6, 'b'), (6, 10, 'a')]
    assert m.get(5) == 'b'
    m.set(4, 6, 'a')
    assert m.items() == [(0, 10, 'a')]
    m.set(3, 3, 'z')
    assert m.items() == [(0, 10, 'a')]
    m.set(0, 4, 'c')
    assert m.items() == [(0, 4, 'c'), (4, 10, 'a')]
    p = IntervalMap()
    p.set(0, 2, 'a')
    p.set(2, 4, 'b')
    p.set(4, 6, 'b')
    assert p.items() == [(0, 2, 'a'), (2, 6, 'b')]
    n = IntervalMap()
    n.set(0, 5, 'x')
    n.set(5, 9, 'x')
    assert n.items() == [(0, 9, 'x')]
    n.set(3, 7, 'y')
    assert n.items() == [(0, 3, 'x'), (3, 7, 'y'), (7, 9, 'x')]
    _err = False
    try:
        n.set(5, 1, 'q')
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    class IntervalMap:
        def __init__(self):
            self._spans = []

        def set(self, lo, hi, value):
            if lo > hi:
                raise ValueError('lo must not exceed hi')
            if lo == hi:
                return
            kept = []
            for a, b, v in self._spans:
                if a < lo:
                    kept.append((a, min(b, lo), v))
                if b > hi:
                    kept.append((max(a, hi), b, v))
            kept.append((lo, hi, value))
            kept.sort(key=lambda span: span[0])
            self._spans = kept

        def get(self, x):
            for a, b, v in self._spans:
                if a <= x < b:
                    return v
            return None

        def items(self):
            merged = []
            for a, b, v in self._spans:
                if merged and merged[-1][1] == a and merged[-1][2] == v:
                    merged[-1] = (merged[-1][0], b, v)
                else:
                    merged.append((a, b, v))
            return merged
    """,
))

SPECS.append(spec(
    id="cal05",
    title="SlidingWindowCounter",
    difficulty="medium",
    objective="""
    class SlidingWindowCounter

    Counts events over a moving window. The constructor takes the window
    length and raises ValueError if it is not positive. Support:

      add(timestamp, count=1) — record `count` events at that timestamp.
      Timestamps arrive in non-decreasing order; one that goes backwards
      raises ValueError.

      total(now) — the number of events whose timestamp lies in the half-open
      window that begins `window` units before now and ends at now, with the
      earlier end included and now itself excluded.

      prune(now) — discard every recorded event older than the start of that
      window and return how many were discarded.
    """,
    holdout_test="""
    c = SlidingWindowCounter(10)
    assert c.total(100) == 0
    c.add(90)
    c.add(95, 1)
    c.add(95, 2)
    assert c.total(100) == 4
    assert c.total(91) == 1
    c.add(100)
    assert c.total(100) == 4
    assert c.total(101) == 4
    assert c.total(110) == 1
    assert c.prune(101) == 1
    assert c.total(101) == 4
    assert c.prune(105) == 0
    assert c.prune(200) == 3
    assert c.total(200) == 0
    w = SlidingWindowCounter(1)
    w.add(0, 5)
    assert w.total(1) == 5
    assert w.total(2) == 0
    _bad = 0
    try:
        c.add(5)
    except ValueError:
        _bad += 1
    try:
        SlidingWindowCounter(0)
    except ValueError:
        _bad += 1
    assert _bad == 2
    """,
    reference="""
    class SlidingWindowCounter:
        def __init__(self, window):
            if window <= 0:
                raise ValueError('window must be positive')
            self.window = window
            self._events = []
            self._last = None

        def add(self, timestamp, count=1):
            if self._last is not None and timestamp < self._last:
                raise ValueError('timestamps must not go backwards')
            self._last = timestamp
            self._events.append((timestamp, count))

        def total(self, now):
            low = now - self.window
            return sum(c for t, c in self._events if low <= t < now)

        def prune(self, now):
            low = now - self.window
            before = len(self._events)
            self._events = [(t, c) for t, c in self._events if t >= low]
            return before - len(self._events)
    """,
))

SPECS.append(spec(
    id="cal06",
    title="TokenBucket",
    difficulty="hard",
    objective="""
    class TokenBucket

    A rate limiter. The constructor takes a capacity and a refill rate in
    tokens per unit of time, raising ValueError if either is not positive, and
    the bucket starts full at time zero. Support:

      tokens(now) — the number of tokens available at that time, as a float.
      Tokens accrue at the refill rate for the time elapsed since the last
      call and never exceed the capacity.

      take(n, now) — if at least n tokens are available at that time, remove
      them and return True; otherwise leave the bucket alone and return False.
      A request larger than the capacity could never be granted, so it raises
      ValueError instead.

    Time never runs backwards: a time earlier than one already seen raises
    ValueError.
    """,
    holdout_test="""
    b = TokenBucket(10, 2)
    assert b.tokens(0) == 10.0
    assert b.take(10, 0) is True
    assert b.tokens(0) == 0.0
    assert b.take(1, 0) is False
    assert b.tokens(0.5) == 1.0
    assert b.take(1, 0.5) is True
    assert b.tokens(0.5) == 0.0
    assert b.tokens(100) == 10.0
    assert b.take(4, 100) is True
    assert b.tokens(100) == 6.0
    tiny = TokenBucket(1, 1)
    assert tiny.take(1, 0) is True
    assert tiny.tokens(0) == 0.0
    assert tiny.tokens(4) == 1.0
    _bad = 0
    try:
        b.take(11, 100)
    except ValueError:
        _bad += 1
    try:
        b.tokens(99)
    except ValueError:
        _bad += 1
    try:
        TokenBucket(0, 1)
    except ValueError:
        _bad += 1
    try:
        TokenBucket(10, 0)
    except ValueError:
        _bad += 1
    assert _bad == 4
    """,
    reference="""
    class TokenBucket:
        def __init__(self, capacity, refill_rate):
            if capacity <= 0 or refill_rate <= 0:
                raise ValueError('capacity and refill_rate must be positive')
            self.capacity = float(capacity)
            self.refill_rate = float(refill_rate)
            self._tokens = float(capacity)
            self._stamp = 0.0

        def _advance(self, now):
            if now < self._stamp:
                raise ValueError('time must not go backwards')
            self._tokens = min(self.capacity, self._tokens + (now - self._stamp) * self.refill_rate)
            self._stamp = now

        def tokens(self, now):
            self._advance(now)
            return self._tokens

        def take(self, n, now):
            if n > self.capacity:
                raise ValueError('request exceeds capacity')
            self._advance(now)
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False
    """,
))

SPECS.append(spec(
    id="cal07",
    title="free_slots",
    difficulty="hard",
    objective="""
    def free_slots(busy: list, start: int, end: int, minimum: int) -> list

    Each element of busy is a [from, to] pair describing an occupied half-open
    interval; they arrive in no particular order and may overlap or nest.
    Return the gaps inside the half-open window from start to end during which
    nothing is occupied, as a list of fresh [from, to] pairs in increasing
    order, keeping only those at least `minimum` long.

    Busy time outside the window is irrelevant, and a busy interval that only
    partly overlaps the window blocks only the part inside it. The argument
    must not be modified. A minimum that is not positive raises ValueError.
    """,
    holdout_test="""
    _src = [[3, 5], [1, 2]]
    _copy = [list(x) for x in _src]
    assert free_slots(_src, 0, 10, 1) == [[0, 1], [2, 3], [5, 10]]
    assert _src == _copy
    assert free_slots([], 0, 5, 1) == [[0, 5]]
    assert free_slots([[0, 5]], 0, 5, 1) == []
    assert free_slots([[1, 2], [1, 4]], 0, 6, 2) == [[4, 6]]
    assert free_slots([[2, 3]], 0, 10, 8) == []
    assert free_slots([[-5, 1], [9, 20]], 0, 10, 1) == [[1, 9]]
    assert free_slots([[2, 4], [4, 6]], 0, 8, 2) == [[0, 2], [6, 8]]
    assert free_slots([[0, 1]], 0, 3, 2) == [[1, 3]]
    assert free_slots([[3, 3]], 0, 10, 2) == [[0, 10]]
    assert free_slots([[12, 20]], 0, 10, 1) == [[0, 10]]
    assert free_slots([[-5, -1]], 0, 10, 1) == [[0, 10]]
    _err = False
    try:
        free_slots([], 0, 5, 0)
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def free_slots(busy, start, end, minimum):
        if minimum <= 0:
            raise ValueError('minimum must be positive')
        spans = sorted((max(item[0], start), min(item[1], end)) for item in busy)
        out = []
        cursor = start
        for a, b in spans:
            if b <= a:
                continue
            if a - cursor >= minimum:
                out.append([cursor, a])
            cursor = max(cursor, b)
        if end - cursor >= minimum:
            out.append([cursor, end])
        return out
    """,
))

SPECS.append(spec(
    id="cal08",
    title="interval_intersection",
    difficulty="medium",
    objective="""
    def interval_intersection(a: list, b: list) -> list

    Both arguments are lists of [from, to] pairs describing half-open
    intervals, already sorted and already disjoint within each list. Return
    the intervals covered by both, as fresh pairs in increasing order.

    Because the intervals are half-open, two that merely touch at a point
    share nothing and contribute no result. Neither argument may be modified.
    """,
    holdout_test="""
    _a = [[0, 2], [5, 10], [13, 23]]
    _b = [[1, 5], [8, 12], [15, 24], [25, 26]]
    _before = [list(x) for x in _a]
    assert interval_intersection(_a, _b) == [[1, 2], [8, 10], [15, 23]]
    assert _a == _before
    assert interval_intersection([], [[1, 2]]) == []
    assert interval_intersection([[1, 2]], []) == []
    assert interval_intersection([[1, 3]], [[3, 5]]) == []
    assert interval_intersection([[1, 5]], [[2, 3], [4, 9]]) == [[2, 3], [4, 5]]
    assert interval_intersection([[0, 10]], [[0, 10]]) == [[0, 10]]
    assert interval_intersection([[0, 1], [2, 3]], [[0, 3]]) == [[0, 1], [2, 3]]
    _out = interval_intersection([[0, 4]], [[1, 2]])
    _out[0][0] = 99
    assert interval_intersection([[0, 4]], [[1, 2]]) == [[1, 2]]
    """,
    reference="""
    def interval_intersection(a, b):
        i = 0
        j = 0
        out = []
        while i < len(a) and j < len(b):
            lo = max(a[i][0], b[j][0])
            hi = min(a[i][1], b[j][1])
            if lo < hi:
                out.append([lo, hi])
            if a[i][1] <= b[j][1]:
                i += 1
            else:
                j += 1
        return out
    """,
))

SPECS.append(spec(
    id="cal09",
    title="count_subarrays_with_sum",
    difficulty="hard",
    objective="""
    def count_subarrays_with_sum(nums: list, target: int) -> int

    Count the contiguous stretches of nums, including single elements, whose
    values add up to target. Two stretches that cover different positions
    count separately even when they hold the same numbers.

    The values are arbitrary integers: negatives and zeros are ordinary
    inputs, not edge cases, and an empty stretch is never counted.
    """,
    holdout_test="""
    assert count_subarrays_with_sum([], 0) == 0
    assert count_subarrays_with_sum([1, 1, 1], 2) == 2
    assert count_subarrays_with_sum([1, 2, 3], 3) == 2
    assert count_subarrays_with_sum([3, 4, 7, 2, -3, 1, 4, 2], 7) == 4
    assert count_subarrays_with_sum([1, -1, 0], 0) == 3
    assert count_subarrays_with_sum([0, 0, 0], 0) == 6
    assert count_subarrays_with_sum([-1, -1, 1], -2) == 1
    assert count_subarrays_with_sum([5], 5) == 1
    assert count_subarrays_with_sum([5], 0) == 0
    assert count_subarrays_with_sum([2, -2, 2, -2], 0) == 4
    """,
    reference="""
    def count_subarrays_with_sum(nums, target):
        seen = {0: 1}
        running = 0
        found = 0
        for value in nums:
            running += value
            found += seen.get(running - target, 0)
            seen[running] = seen.get(running, 0) + 1
        return found
    """,
))

SPECS.append(spec(
    id="cal10",
    title="longest_k_distinct",
    difficulty="hard",
    objective="""
    def longest_k_distinct(s: str, k: int) -> str

    Return the longest stretch of consecutive characters of s that uses no
    more than k different characters. When several stretches tie for longest,
    return the one that starts earliest. A k of zero admits only the empty
    stretch; a negative k raises ValueError.
    """,
    holdout_test="""
    assert longest_k_distinct('', 3) == ''
    assert longest_k_distinct('abc', 0) == ''
    assert longest_k_distinct('eceba', 2) == 'ece'
    assert longest_k_distinct('aa', 1) == 'aa'
    assert longest_k_distinct('abaccc', 2) == 'accc'
    assert longest_k_distinct('abcabc', 3) == 'abcabc'
    assert longest_k_distinct('abab', 1) == 'a'
    assert longest_k_distinct('aabbcc', 2) == 'aabb'
    assert longest_k_distinct('xyz', 5) == 'xyz'
    _err = False
    try:
        longest_k_distinct('abc', -1)
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def longest_k_distinct(s, k):
        if k < 0:
            raise ValueError('k must not be negative')
        if k == 0:
            return ''
        counts = {}
        left = 0
        best = (0, 0)
        for right, ch in enumerate(s):
            counts[ch] = counts.get(ch, 0) + 1
            while len(counts) > k:
                drop = s[left]
                counts[drop] -= 1
                if counts[drop] == 0:
                    del counts[drop]
                left += 1
            if right + 1 - left > best[1] - best[0]:
                best = (left, right + 1)
        return s[best[0]:best[1]]
    """,
))

SPECS.append(spec(
    id="cal11",
    title="spell_number",
    difficulty="hard",
    objective="""
    def spell_number(n: int) -> str

    Spell a whole number from 0 to 999999 in lowercase British-free American
    English: no comma, no 'and', a hyphen inside a compound tens word such as
    the numbers from twenty-one upwards, and a single space between the other
    parts. The word for the thousands is followed by the word thousand and
    then the remainder, which is omitted entirely when it is zero.

    Anything outside that range raises ValueError.
    """,
    holdout_test="""
    assert spell_number(0) == 'zero'
    assert spell_number(7) == 'seven'
    assert spell_number(13) == 'thirteen'
    assert spell_number(21) == 'twenty-one'
    assert spell_number(40) == 'forty'
    assert spell_number(100) == 'one hundred'
    assert spell_number(105) == 'one hundred five'
    assert spell_number(999) == 'nine hundred ninety-nine'
    assert spell_number(1000) == 'one thousand'
    assert spell_number(1001) == 'one thousand one'
    assert spell_number(21000) == 'twenty-one thousand'
    assert spell_number(999999) == 'nine hundred ninety-nine thousand nine hundred ninety-nine'
    _err = 0
    try:
        spell_number(-1)
    except ValueError:
        _err += 1
    try:
        spell_number(1000000)
    except ValueError:
        _err += 1
    assert _err == 2
    """,
    reference="""
    def spell_number(n):
        if n < 0 or n > 999999:
            raise ValueError('out of range')
        ones = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven',
                'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen',
                'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen',
                'nineteen']
        tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty',
                'seventy', 'eighty', 'ninety']

        def small(v):
            parts = []
            if v >= 100:
                parts.append(ones[v // 100] + ' hundred')
                v = v % 100
            if v >= 20:
                word = tens[v // 10]
                if v % 10:
                    word = word + '-' + ones[v % 10]
                parts.append(word)
            elif v > 0:
                parts.append(ones[v])
            return ' '.join(parts)

        if n == 0:
            return 'zero'
        if n < 1000:
            return small(n)
        head = small(n // 1000) + ' thousand'
        rest = n % 1000
        if rest == 0:
            return head
        return head + ' ' + small(rest)
    """,
))

SPECS.append(spec(
    id="cal12",
    title="parse_csv_records",
    difficulty="hard",
    objective="""
    def parse_csv_records(text: str) -> list

    Split comma-separated text into rows, each a list of field strings.

    A field that begins with a double quote is quoted: it runs to the matching
    quote and may contain commas and line breaks, and a doubled quote inside
    it means one literal quote. A quote appearing anywhere else is an ordinary
    character. Rows are separated by a line feed or by a carriage return and
    line feed together; a line break at the very end of the text does not
    introduce an extra row, but an empty line in the middle is a row holding
    one empty field.

    Text that ends inside a quoted field raises ValueError.
    """,
    holdout_test="""
    assert parse_csv_records('') == []
    assert parse_csv_records('a,b,c') == [['a', 'b', 'c']]
    assert parse_csv_records('a,b\\n') == [['a', 'b']]
    assert parse_csv_records('a,,c') == [['a', '', 'c']]
    assert parse_csv_records('a\\r\\nb') == [['a'], ['b']]
    assert parse_csv_records('a\\n\\nb') == [['a'], [''], ['b']]
    assert parse_csv_records('"a,b",c') == [['a,b', 'c']]
    assert parse_csv_records('"a""b"') == [['a"b']]
    assert parse_csv_records('"x\\ny"') == [['x\\ny']]
    assert parse_csv_records('a"b') == [['a"b']]
    assert parse_csv_records('"",x') == [['', 'x']]
    _err = False
    try:
        parse_csv_records('"abc')
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def parse_csv_records(text):
        rows = []
        row = []
        field = []
        pending = False
        quoted = False
        i = 0
        size = len(text)
        while i < size:
            ch = text[i]
            if quoted:
                if ch == '"':
                    if i + 1 < size and text[i + 1] == '"':
                        field.append('"')
                        i += 2
                        continue
                    quoted = False
                    i += 1
                    continue
                field.append(ch)
                i += 1
                continue
            if ch == '"' and not field:
                quoted = True
                pending = True
                i += 1
                continue
            if ch == ',':
                row.append(''.join(field))
                field = []
                pending = True
                i += 1
                continue
            if ch == '\\n' or (ch == '\\r' and i + 1 < size and text[i + 1] == '\\n'):
                row.append(''.join(field))
                rows.append(row)
                row = []
                field = []
                pending = False
                i += 2 if ch == '\\r' else 1
                continue
            field.append(ch)
            pending = True
            i += 1
        if quoted:
            raise ValueError('unterminated quoted field')
        if pending or field or row:
            row.append(''.join(field))
            rows.append(row)
        return rows
    """,
))

SPECS.append(spec(
    id="cal13",
    title="parse_ini",
    difficulty="medium",
    objective="""
    def parse_ini(text: str) -> dict

    Read INI-style configuration into a dictionary of sections, each of which
    is a dictionary of string keys to string values.

    A line in square brackets opens a section, and its name is stripped of
    surrounding blank space. Elsewhere a line is a key, an equals sign and a
    value; only the first equals sign separates them, and both sides lose
    their surrounding blank space. Blank lines are skipped, as are lines whose
    first non-blank character is a semicolon or a hash. Settings appearing
    before any section belong to a section whose name is the empty string,
    which is absent from the result when nothing was assigned to it. A section
    that is opened but never assigned to is still present, and empty.

    A malformed header, a line that is not a pair, an empty key, and a key
    assigned twice in the same section all raise ValueError.
    """,
    holdout_test="""
    assert parse_ini('') == {}
    assert parse_ini('a=1') == {'': {'a': '1'}}
    assert parse_ini('[s]\\nk = v') == {'s': {'k': 'v'}}
    assert parse_ini('[s]\\n\\n; note\\n# note\\nk=v') == {'s': {'k': 'v'}}
    assert parse_ini('[s]\\nk=a=b') == {'s': {'k': 'a=b'}}
    assert parse_ini('[ s ]\\nk=v') == {'s': {'k': 'v'}}
    assert parse_ini('[s]') == {'s': {}}
    assert parse_ini('[a]\\nk=1\\n[b]\\nk=2') == {'a': {'k': '1'}, 'b': {'k': '2'}}
    assert parse_ini('x=1\\n[a]\\ny=2') == {'': {'x': '1'}, 'a': {'y': '2'}}
    _bad = 0
    for _text in ['[s]\\nk=1\\nk=2', '[s\\nk=1', '[s]\\nnope', '[s]\\n=1']:
        try:
            parse_ini(_text)
        except ValueError:
            _bad += 1
    assert _bad == 4
    """,
    reference="""
    def parse_ini(text):
        out = {'': {}}
        section = ''
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line[0] in ';#':
                continue
            if line.startswith('['):
                if not line.endswith(']'):
                    raise ValueError('bad section header')
                section = line[1:-1].strip()
                out.setdefault(section, {})
                continue
            if '=' not in line:
                raise ValueError('not a key/value pair')
            key, value = line.split('=', 1)
            key = key.strip()
            if not key:
                raise ValueError('empty key')
            if key in out[section]:
                raise ValueError('duplicate key')
            out[section][key] = value.strip()
        if not out['']:
            del out['']
        return out
    """,
))

SPECS.append(spec(
    id="cal14",
    title="render_template",
    difficulty="medium",
    objective="""
    def render_template(template: str, values: dict) -> str

    Substitute placeholders in template. A name between single braces is
    replaced by the matching entry of values, converted to a string. A doubled
    opening or closing brace stands for one literal brace and is never treated
    as a placeholder.

    A name with no entry in values raises KeyError carrying that name, and a
    brace with no partner raises ValueError.
    """,
    holdout_test="""
    assert render_template('', {}) == ''
    assert render_template('hi', {}) == 'hi'
    assert render_template('{a}', {'a': 'x'}) == 'x'
    assert render_template('{a}{b}', {'a': '1', 'b': '2'}) == '12'
    assert render_template('a {n} b', {'n': 7}) == 'a 7 b'
    assert render_template('{{a}}', {}) == '{a}'
    assert render_template('{{{a}}}', {'a': 'z'}) == '{z}'
    assert render_template('100{{%}}', {}) == '100{%}'
    _missing = None
    try:
        render_template('{who}', {'a': 1})
    except KeyError as exc:
        _missing = exc.args[0]
    assert _missing == 'who'
    _bad = 0
    for _text in ['{a', 'a}']:
        try:
            render_template(_text, {'a': 1})
        except ValueError:
            _bad += 1
    assert _bad == 2
    """,
    reference="""
    def render_template(template, values):
        out = []
        i = 0
        size = len(template)
        while i < size:
            ch = template[i]
            if ch == '{':
                if i + 1 < size and template[i + 1] == '{':
                    out.append('{')
                    i += 2
                    continue
                end = template.find('}', i + 1)
                if end < 0:
                    raise ValueError('unmatched brace')
                name = template[i + 1:end]
                if name not in values:
                    raise KeyError(name)
                out.append(str(values[name]))
                i = end + 1
                continue
            if ch == '}':
                if i + 1 < size and template[i + 1] == '}':
                    out.append('}')
                    i += 2
                    continue
                raise ValueError('unmatched brace')
            out.append(ch)
            i += 1
        return ''.join(out)
    """,
))

SPECS.append(spec(
    id="cal15",
    title="resolve_path",
    difficulty="medium",
    objective="""
    def resolve_path(base: str, path: str) -> str

    Resolve a slash-separated path against an absolute base directory, purely
    as text: nothing is looked up on disk.

    A path that starts with a slash ignores the base. A single dot is the
    current directory, two dots move to the parent, repeated slashes are the
    same as one, and the result is absolute with no trailing slash unless it
    is the root itself.

    A base that is not absolute raises ValueError, and so does any path that
    would climb above the root.
    """,
    holdout_test="""
    assert resolve_path('/a/b', 'c') == '/a/b/c'
    assert resolve_path('/a/b', '../c') == '/a/c'
    assert resolve_path('/a/b', '/x/y') == '/x/y'
    assert resolve_path('/', 'a') == '/a'
    assert resolve_path('/a', '.') == '/a'
    assert resolve_path('/a', '') == '/a'
    assert resolve_path('/a/b', '../../') == '/'
    assert resolve_path('/a//b', 'c//d') == '/a/b/c/d'
    assert resolve_path('/a', './b/../c') == '/a/c'
    assert resolve_path('/a/b/', 'c/') == '/a/b/c'
    _bad = 0
    try:
        resolve_path('/a', '../..')
    except ValueError:
        _bad += 1
    try:
        resolve_path('a', 'b')
    except ValueError:
        _bad += 1
    assert _bad == 2
    """,
    reference="""
    def resolve_path(base, path):
        if not base.startswith('/'):
            raise ValueError('base must be absolute')
        parts = path.split('/') if path.startswith('/') else (base + '/' + path).split('/')
        stack = []
        for part in parts:
            if part == '' or part == '.':
                continue
            if part == '..':
                if not stack:
                    raise ValueError('path escapes the root')
                stack.pop()
                continue
            stack.append(part)
        return '/' + '/'.join(stack)
    """,
))

SPECS.append(spec(
    id="cal16",
    title="parse_cli_args",
    difficulty="medium",
    objective="""
    def parse_cli_args(argv: list) -> tuple

    Split a command line into a dictionary of options and a list of
    positional arguments, returned in that order as a two-element tuple.

    A word beginning with two dashes is a long option; if it contains an
    equals sign the text after the first one is its value, otherwise its value
    is the boolean True. A word beginning with one dash and carrying at least
    one more character is a cluster of single-letter options, each True. A
    lone double dash ends option parsing and everything after it is
    positional. Anything else, including a bare dash, is positional.

    A long option with an empty name raises ValueError.
    """,
    holdout_test="""
    assert parse_cli_args([]) == ({}, [])
    assert parse_cli_args(['a', 'b']) == ({}, ['a', 'b'])
    assert parse_cli_args(['--x']) == ({'x': True}, [])
    assert parse_cli_args(['--x=1']) == ({'x': '1'}, [])
    assert parse_cli_args(['--x=']) == ({'x': ''}, [])
    assert parse_cli_args(['--x=a=b']) == ({'x': 'a=b'}, [])
    assert parse_cli_args(['-ab']) == ({'a': True, 'b': True}, [])
    assert parse_cli_args(['-']) == ({}, ['-'])
    assert parse_cli_args(['--', '--x', '-a']) == ({}, ['--x', '-a'])
    assert parse_cli_args(['p', '--x', 'q']) == ({'x': True}, ['p', 'q'])
    _bad = False
    try:
        parse_cli_args(['--=v'])
    except ValueError:
        _bad = True
    assert _bad is True
    """,
    reference="""
    def parse_cli_args(argv):
        flags = {}
        rest = []
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg == '--':
                rest.extend(argv[i + 1:])
                break
            if arg.startswith('--'):
                body = arg[2:]
                if '=' in body:
                    name, value = body.split('=', 1)
                else:
                    name, value = body, True
                if not name:
                    raise ValueError('empty option name')
                flags[name] = value
            elif arg.startswith('-') and len(arg) > 1:
                for ch in arg[1:]:
                    flags[ch] = True
            else:
                rest.append(arg)
            i += 1
        return flags, rest
    """,
))

SPECS.append(spec(
    id="cal17",
    title="expand_braces",
    difficulty="hard",
    objective="""
    def expand_braces(pattern: str) -> list

    Expand shell-style brace alternatives into every string the pattern can
    produce, in order.

    A braced group holds alternatives separated by commas; an alternative may
    be empty, and a group may contain further groups, whose commas belong to
    the inner group. Several groups in one pattern combine, with the leftmost
    group varying most slowly. A comma outside any group is an ordinary
    character, and a pattern with no group produces itself.

    A brace with no partner raises ValueError.
    """,
    holdout_test="""
    assert expand_braces('a') == ['a']
    assert expand_braces('') == ['']
    assert expand_braces('{a,b}') == ['a', 'b']
    assert expand_braces('a{b,c}d') == ['abd', 'acd']
    assert expand_braces('a{,x}') == ['a', 'ax']
    assert expand_braces('{}') == ['']
    assert expand_braces('{a,b}{c,d}') == ['ac', 'ad', 'bc', 'bd']
    assert expand_braces('{a,{b,c}}') == ['a', 'b', 'c']
    assert expand_braces('x{a,{b,c}d}y') == ['xay', 'xbdy', 'xcdy']
    assert expand_braces('a,b') == ['a,b']
    _bad = 0
    for _text in ['{a', 'a}', '{a,{b}']:
        try:
            expand_braces(_text)
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def expand_braces(pattern):
        depth = 0
        start = -1
        end = -1
        for i, ch in enumerate(pattern):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                if depth == 0:
                    raise ValueError('unmatched brace')
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if depth:
            raise ValueError('unmatched brace')
        if end < 0:
            return [pattern]
        prefix = pattern[:start]
        body = pattern[start + 1:end]
        suffix = pattern[end + 1:]
        options = []
        current = []
        inner = 0
        for ch in body:
            if ch == ',' and inner == 0:
                options.append(''.join(current))
                current = []
                continue
            if ch == '{':
                inner += 1
            elif ch == '}':
                inner -= 1
            current.append(ch)
        options.append(''.join(current))
        out = []
        for option in options:
            out.extend(expand_braces(prefix + option + suffix))
        return out
    """,
))

SPECS.append(spec(
    id="cal18",
    title="expand_cron_field",
    difficulty="hard",
    objective="""
    def expand_cron_field(field: str, low: int, high: int) -> list

    Expand one field of a cron schedule into the sorted list of distinct
    values it selects, where low and high are the inclusive bounds for that
    field.

    A field is a comma-separated list of terms. A term is a star meaning the
    whole range, a plain number, or a range written as two numbers joined by a
    hyphen. Any term may be followed by a slash and a step, which takes every
    step-th value from the start of that term's range rather than every one.

    An empty term, a term that is not one of those forms, a reversed range, a
    value outside the bounds, and a step that is not a positive number all
    raise ValueError, as do bounds given the wrong way round.
    """,
    holdout_test="""
    assert expand_cron_field('*', 0, 5) == [0, 1, 2, 3, 4, 5]
    assert expand_cron_field('*/2', 0, 5) == [0, 2, 4]
    assert expand_cron_field('1-3', 0, 5) == [1, 2, 3]
    assert expand_cron_field('1-5/2', 0, 5) == [1, 3, 5]
    assert expand_cron_field('4', 0, 5) == [4]
    assert expand_cron_field('3,1,1', 0, 5) == [1, 3]
    assert expand_cron_field('0-1,4-5', 0, 5) == [0, 1, 4, 5]
    assert expand_cron_field('*', 1, 1) == [1]
    assert expand_cron_field('2-2', 0, 5) == [2]
    assert expand_cron_field('*/1', 3, 5) == [3, 4, 5]
    _bad = 0
    for _term in ['6', '3-1', '*/0', 'x', '', '1,,2', '+1', '*/+2', '1-2-3', '+1-3']:
        try:
            expand_cron_field(_term, 0, 5)
        except ValueError:
            _bad += 1
    assert _bad == 10
    _reversed = False
    try:
        expand_cron_field('*', 5, 0)
    except ValueError:
        _reversed = True
    assert _reversed is True
    """,
    reference="""
    def expand_cron_field(field, low, high):
        if low > high:
            raise ValueError('bounds are reversed')
        values = set()
        for part in field.split(','):
            part = part.strip()
            step = 1
            if '/' in part:
                part, raw = part.split('/', 1)
                if not raw.isdigit():
                    raise ValueError('bad step')
                step = int(raw)
                if step == 0:
                    raise ValueError('step must not be zero')
            if part == '*':
                start = low
                stop = high
            elif '-' in part:
                pieces = part.split('-')
                if len(pieces) != 2 or not (pieces[0].isdigit() and pieces[1].isdigit()):
                    raise ValueError('bad range')
                start = int(pieces[0])
                stop = int(pieces[1])
            else:
                if not part.isdigit():
                    raise ValueError('bad value')
                start = int(part)
                stop = start
            if start > stop or start < low or stop > high:
                raise ValueError('out of range')
            values.update(range(start, stop + 1, step))
        return sorted(values)
    """,
))

SPECS.append(spec(
    id="cal19",
    title="parse_iso_duration",
    difficulty="hard",
    objective="""
    def parse_iso_duration(text: str) -> int

    Convert an ISO 8601 duration to a whole number of seconds.

    The string opens with the letter P. Before an optional T come amounts in
    weeks and days; after it come hours, minutes and seconds. Each amount is a
    run of digits followed by the single letter naming its unit, a week is
    seven days and a day is twenty-four hours, and the units that are present
    must appear in decreasing size.

    A string that does not open with P, one that carries no amount at all, a
    T with nothing after it, digits with no unit, a unit with no digits, a
    time unit in the date part or the other way round, and units out of order
    all raise ValueError. Fractions are not accepted.
    """,
    holdout_test="""
    assert parse_iso_duration('PT1S') == 1
    assert parse_iso_duration('PT0S') == 0
    assert parse_iso_duration('PT1M') == 60
    assert parse_iso_duration('PT1H30M') == 5400
    assert parse_iso_duration('P1D') == 86400
    assert parse_iso_duration('P1DT1S') == 86401
    assert parse_iso_duration('P2W') == 1209600
    assert parse_iso_duration('P1W2DT3H4M5S') == 788645
    assert parse_iso_duration('PT90M') == 5400
    _bad = 0
    for _text in ['1D', 'P', 'PT', 'P1S', 'PT1M1H', 'PT1', 'PT1.5S', 'PD']:
        try:
            parse_iso_duration(_text)
        except ValueError:
            _bad += 1
    assert _bad == 8
    """,
    reference="""
    def parse_iso_duration(text):
        if not text.startswith('P'):
            raise ValueError('must start with P')
        body = text[1:]
        date_part, sep, time_part = body.partition('T')
        if sep and not time_part:
            raise ValueError('empty time part')
        state = {'total': 0, 'found': False}

        def consume(chunk, table, order):
            digits = ''
            seen = ''
            for ch in chunk:
                if ch.isdigit():
                    digits = digits + ch
                    continue
                if ch not in table:
                    raise ValueError('unknown unit')
                if not digits:
                    raise ValueError('missing amount')
                if seen and order.index(ch) <= order.index(seen):
                    raise ValueError('units out of order')
                seen = ch
                state['total'] += int(digits) * table[ch]
                state['found'] = True
                digits = ''
            if digits:
                raise ValueError('digits without a unit')

        consume(date_part, {'W': 604800, 'D': 86400}, 'WD')
        consume(time_part, {'H': 3600, 'M': 60, 'S': 1}, 'HMS')
        if not state['found']:
            raise ValueError('empty duration')
        return state['total']
    """,
))

SPECS.append(spec(
    id="cal20",
    title="column_label",
    difficulty="medium",
    objective="""
    def column_label(n: int) -> str
    def column_index(label: str) -> int

    Write both. Spreadsheet columns are numbered from one and labelled with
    uppercase letters: the first twenty-six are single letters, and after that
    the labels grow a place, cycling through every combination in order. There
    is no zero digit, so the counting is not ordinary base twenty-six.

    column_label turns a number into its label and column_index turns a label
    back into its number; each is the other's inverse. A number below one, and
    a label that is not one or more uppercase letters, raise ValueError.
    """,
    holdout_test="""
    assert column_label(1) == 'A'
    assert column_label(26) == 'Z'
    assert column_label(27) == 'AA'
    assert column_label(52) == 'AZ'
    assert column_label(53) == 'BA'
    assert column_label(702) == 'ZZ'
    assert column_label(703) == 'AAA'
    assert column_index('A') == 1
    assert column_index('Z') == 26
    assert column_index('AA') == 27
    assert column_index('ZZ') == 702
    assert all(column_index(column_label(_n)) == _n for _n in range(1, 800))
    _bad = 0
    for _call in [lambda: column_label(0), lambda: column_label(-3),
                  lambda: column_index(''), lambda: column_index('a'),
                  lambda: column_index('A1')]:
        try:
            _call()
        except ValueError:
            _bad += 1
    assert _bad == 5
    """,
    reference="""
    def column_label(n):
        if n < 1:
            raise ValueError('n must be positive')
        out = ''
        while n > 0:
            n, rest = divmod(n - 1, 26)
            out = chr(65 + rest) + out
        return out

    def column_index(label):
        if not label or not label.isalpha() or not label.isupper():
            raise ValueError('bad label')
        total = 0
        for ch in label:
            total = total * 26 + (ord(ch) - 64)
        return total
    """,
))

SPECS.append(spec(
    id="cal21",
    title="validate_isbn",
    difficulty="medium",
    objective="""
    def validate_isbn(code: str) -> bool

    Report whether a book number is well formed. Hyphens and spaces are
    decoration and are ignored.

    A ten-character number is valid when the sum of its digits, each weighted
    by its position counting down from ten, is a multiple of eleven; in that
    form only, the final character may be an X standing for the value ten. A
    thirteen-character number is all digits and is valid when the sum of its
    digits, alternately weighted one and three starting with one, is a
    multiple of ten.

    Anything else — another length, a stray letter, a misplaced X — is simply
    invalid rather than an error.
    """,
    holdout_test="""
    assert validate_isbn('0306406152') is True
    assert validate_isbn('0-306-40615-2') is True
    assert validate_isbn('0 306 40615 2') is True
    assert validate_isbn('043942089X') is True
    assert validate_isbn('0306406153') is False
    assert validate_isbn('043942089x') is False
    assert validate_isbn('04394X089X') is False
    assert validate_isbn('9780306406157') is True
    assert validate_isbn('9783161484100') is True
    assert validate_isbn('9780306406158') is False
    assert validate_isbn('978030640615X') is False
    assert validate_isbn('') is False
    assert validate_isbn('12345') is False
    """,
    reference="""
    def validate_isbn(code):
        cleaned = code.replace('-', '').replace(' ', '')
        if len(cleaned) == 10:
            total = 0
            for i, ch in enumerate(cleaned):
                if ch == 'X' and i == 9:
                    value = 10
                elif ch.isdigit():
                    value = int(ch)
                else:
                    return False
                total += value * (10 - i)
            return total % 11 == 0
        if len(cleaned) == 13:
            if not cleaned.isdigit():
                return False
            total = 0
            for i, ch in enumerate(cleaned):
                total += int(ch) * (3 if i % 2 else 1)
            return total % 10 == 0
        return False
    """,
))

SPECS.append(spec(
    id="cal22",
    title="sliding_max",
    difficulty="hard",
    objective="""
    def sliding_max(nums: list, k: int) -> list

    Slide a window of exactly k values along nums one position at a time and
    return the largest value in each position of the window, in order. The
    first window covers the first k values, and the result has one entry per
    window.

    A k that is not positive, or larger than the list, raises ValueError. The
    argument must not be modified.
    """,
    holdout_test="""
    assert sliding_max([1, 3, -1, -3, 5, 3, 6, 7], 3) == [3, 3, 5, 5, 6, 7]
    assert sliding_max([1], 1) == [1]
    assert sliding_max([9, 8, 7], 1) == [9, 8, 7]
    assert sliding_max([1, 2, 3], 3) == [3]
    assert sliding_max([3, 3, 3], 2) == [3, 3]
    assert sliding_max([-1, -2], 2) == [-1]
    assert sliding_max([7, 2, 4], 2) == [7, 4]
    assert sliding_max([1, 2, 1, 2, 1], 2) == [2, 2, 2, 2]
    assert sliding_max([5, 4, 3, 2, 1], 2) == [5, 4, 3, 2]
    _src = [4, 1, 4]
    assert sliding_max(_src, 2) == [4, 4]
    assert _src == [4, 1, 4]
    _bad = 0
    for _k in [0, -1, 4]:
        try:
            sliding_max([1, 2, 3], _k)
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def sliding_max(nums, k):
        if k <= 0:
            raise ValueError('k must be positive')
        if k > len(nums):
            raise ValueError('k must not exceed the length')
        out = []
        window = []
        for i, value in enumerate(nums):
            while window and nums[window[-1]] <= value:
                window.pop()
            window.append(i)
            if window[0] <= i - k:
                window.pop(0)
            if i >= k - 1:
                out.append(nums[window[0]])
        return out
    """,
))

SPECS.append(spec(
    id="cal23",
    title="group_anagrams",
    difficulty="medium",
    objective="""
    def group_anagrams(words: list) -> list

    Collect the words that are rearrangements of one another, comparing
    letters without regard to case. A group holds its words in the order they
    appeared in the argument.

    A word that shares its letters with nothing else is not a group and is
    left out entirely. The groups come back largest first, and groups of the
    same size keep the order in which their first word appeared.
    """,
    holdout_test="""
    assert group_anagrams([]) == []
    assert group_anagrams(['abc']) == []
    assert group_anagrams(['ab', 'ba']) == [['ab', 'ba']]
    assert group_anagrams(['ab', 'x', 'ba']) == [['ab', 'ba']]
    assert group_anagrams(['Ab', 'bA']) == [['Ab', 'bA']]
    _words = ['eat', 'tea', 'tan', 'ate', 'nat', 'bat']
    assert group_anagrams(_words) == [['eat', 'tea', 'ate'], ['tan', 'nat']]
    assert group_anagrams(['ab', 'cd', 'ba', 'dc']) == [['ab', 'ba'], ['cd', 'dc']]
    assert group_anagrams(['cd', 'ab', 'dc', 'ba', 'ab']) == [['ab', 'ba', 'ab'], ['cd', 'dc']]
    assert group_anagrams(['a', 'a']) == [['a', 'a']]
    assert group_anagrams(['abc', 'cba', 'bca', 'xy']) == [['abc', 'cba', 'bca']]
    """,
    reference="""
    def group_anagrams(words):
        groups = {}
        order = []
        for word in words:
            key = ''.join(sorted(word.lower()))
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(word)
        out = [groups[key] for key in order if len(groups[key]) > 1]
        out.sort(key=lambda group: -len(group))
        return out
    """,
))

SPECS.append(spec(
    id="cal24",
    title="leaderboard",
    difficulty="medium",
    objective="""
    def leaderboard(scores: list) -> list

    Each element of scores is a (name, points) pair recording one award, and a
    name may be awarded points more than once. Total the points per name and
    return a list of (rank, name, total) tuples, best total first, names in
    alphabetical order among equal totals.

    Ranking is competition style: equal totals share the better rank, and the
    ranks after a tie are pushed down by the size of the tie, so the rank of a
    row is one more than the number of rows strictly ahead of it.
    """,
    holdout_test="""
    assert leaderboard([]) == []
    assert leaderboard([('a', 1)]) == [(1, 'a', 1)]
    assert leaderboard([('a', 1), ('a', 2)]) == [(1, 'a', 3)]
    assert leaderboard([('a', 1), ('b', 2)]) == [(1, 'b', 2), (2, 'a', 1)]
    assert leaderboard([('b', 1), ('a', 1)]) == [(1, 'a', 1), (1, 'b', 1)]
    _rows = leaderboard([('a', 5), ('b', 5), ('c', 3), ('d', 1)])
    assert _rows == [(1, 'a', 5), (1, 'b', 5), (3, 'c', 3), (4, 'd', 1)]
    assert leaderboard([('a', 1), ('b', 1), ('c', 1)]) == [(1, 'a', 1), (1, 'b', 1), (1, 'c', 1)]
    assert leaderboard([('a', 2), ('b', 1), ('c', 1), ('d', 0)]) == [
        (1, 'a', 2), (2, 'b', 1), (2, 'c', 1), (4, 'd', 0)]
    assert leaderboard([('a', -1), ('b', 1)]) == [(1, 'b', 1), (2, 'a', -1)]
    assert leaderboard([('a', 1), ('b', 3), ('a', 3)]) == [(1, 'a', 4), (2, 'b', 3)]
    """,
    reference="""
    def leaderboard(scores):
        totals = {}
        for name, points in scores:
            totals[name] = totals.get(name, 0) + points
        ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        out = []
        previous = None
        rank = 0
        for index, pair in enumerate(ordered):
            if pair[1] != previous:
                rank = index + 1
                previous = pair[1]
            out.append((rank, pair[0], pair[1]))
        return out
    """,
))

SPECS.append(spec(
    id="cal25",
    title="vigenere",
    difficulty="medium",
    objective="""
    def vigenere(text: str, key: str, decode: bool = False) -> str

    Encipher text by shifting each letter forward through the alphabet by the
    position of the corresponding letter of the key, wrapping past the end.
    Case is preserved, and the key repeats over the message.

    Characters that are not letters pass through untouched and, importantly,
    do not consume a letter of the key: the key advances only over letters.
    Decoding shifts backwards instead. A key that is empty or holds anything
    other than letters raises ValueError.
    """,
    holdout_test="""
    assert vigenere('attackatdawn', 'lemon') == 'lxfopvefrnhr'
    assert vigenere('lxfopvefrnhr', 'lemon', True) == 'attackatdawn'
    assert vigenere('', 'abc') == ''
    assert vigenere('abc', 'a') == 'abc'
    assert vigenere('XYZ', 'b') == 'YZA'
    assert vigenere('YZA', 'b', True) == 'XYZ'
    assert vigenere('Hello, World!', 'abc') == 'Hfnlp, Yosnd!'
    assert vigenere('a-b', 'ab') == 'a-c'
    assert vigenere('ABC', 'abc') == 'ACE'
    _bad = 0
    for _key in ['', 'a1', ' ']:
        try:
            vigenere('abc', _key)
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def vigenere(text, key, decode=False):
        if not key or not key.isalpha():
            raise ValueError('key must be one or more letters')
        shifts = [ord(ch.lower()) - 97 for ch in key]
        out = []
        index = 0
        for ch in text:
            if not ch.isalpha():
                out.append(ch)
                continue
            shift = shifts[index % len(shifts)]
            if decode:
                shift = -shift
            base = 65 if ch.isupper() else 97
            out.append(chr((ord(ch) - base + shift) % 26 + base))
            index += 1
        return ''.join(out)
    """,
))

SPECS.append(spec(
    id="cal26",
    title="Ledger",
    difficulty="hard",
    objective="""
    class Ledger

    A double-entry account book. Every account starts at zero. Support:

      balance(account) — the current balance, zero for an account never seen.

      post(account, amount) — add amount, which may be negative or zero, and
      return the new balance. An amount that would take the account below zero
      raises ValueError; a balance of exactly zero is allowed.

      transfer(src, dst, amount) — move a positive amount between two
      different accounts, recording it as two postings. An amount that is not
      positive, a transfer to the same account, and one the source cannot
      cover all raise ValueError, and a rejected transfer must leave both
      balances and the record untouched.

      history() — the postings so far, oldest first, as (account, amount)
      tuples. The caller may modify the returned list without disturbing the
      ledger.
    """,
    holdout_test="""
    book = Ledger()
    assert book.balance('a') == 0
    assert book.history() == []
    assert book.post('a', 100) == 100
    assert book.post('a', -30) == 70
    assert book.balance('a') == 70
    book.transfer('a', 'b', 20)
    assert book.balance('a') == 50
    assert book.balance('b') == 20
    assert book.history() == [('a', 100), ('a', -30), ('a', -20), ('b', 20)]
    book.transfer('a', 'b', 1)
    assert book.balance('a') == 49
    assert book.balance('b') == 21
    assert book.history()[-2:] == [('a', -1), ('b', 1)]
    _snapshot = book.history()
    _snapshot.append(('c', 1))
    assert len(book.history()) == 6
    petty = Ledger()
    assert petty.post('z', 5) == 5
    assert petty.post('z', -5) == 0
    assert petty.balance('z') == 0
    _bad = 0
    for _call in [lambda: petty.post('z', -1), lambda: book.post('a', -50),
                  lambda: book.transfer('a', 'b', 0), lambda: book.transfer('a', 'b', -5),
                  lambda: book.transfer('a', 'a', 5), lambda: book.transfer('a', 'b', 5000)]:
        try:
            _call()
        except ValueError:
            _bad += 1
    assert _bad == 6
    assert book.balance('a') == 49
    assert book.balance('b') == 21
    assert len(book.history()) == 6
    """,
    reference="""
    class Ledger:
        def __init__(self):
            self._balances = {}
            self._entries = []

        def balance(self, account):
            return self._balances.get(account, 0)

        def post(self, account, amount):
            updated = self.balance(account) + amount
            if updated < 0:
                raise ValueError('insufficient funds')
            self._balances[account] = updated
            self._entries.append((account, amount))
            return updated

        def transfer(self, src, dst, amount):
            if amount <= 0:
                raise ValueError('amount must be positive')
            if src == dst:
                raise ValueError('accounts must differ')
            self.post(src, -amount)
            self.post(dst, amount)

        def history(self):
            return list(self._entries)
    """,
))

SPECS.append(spec(
    id="cal27",
    title="UndoStack",
    difficulty="medium",
    objective="""
    class UndoStack

    A text buffer that remembers its own past. It starts empty. Support:

      text() — the current contents.

      append(text) — add text to the end. Anything that had been undone is no
      longer reachable once new text is appended.

      undo() — step back one append, returning True, or return False when
      there is nothing left to undo.

      redo() — step forward again, returning True, or return False when there
      is nothing to redo.
    """,
    holdout_test="""
    u = UndoStack()
    assert u.text() == ''
    assert u.undo() is False
    assert u.redo() is False
    u.append('a')
    u.append('b')
    assert u.text() == 'ab'
    assert u.undo() is True
    assert u.text() == 'a'
    assert u.undo() is True
    assert u.text() == ''
    assert u.undo() is False
    assert u.redo() is True
    assert u.text() == 'a'
    u.append('z')
    assert u.text() == 'az'
    assert u.redo() is False
    assert u.undo() is True
    assert u.text() == 'a'
    """,
    reference="""
    class UndoStack:
        def __init__(self):
            self._states = ['']
            self._index = 0

        def text(self):
            return self._states[self._index]

        def append(self, text):
            self._states = self._states[:self._index + 1]
            self._states.append(self._states[self._index] + text)
            self._index += 1

        def undo(self):
            if self._index == 0:
                return False
            self._index -= 1
            return True

        def redo(self):
            if self._index + 1 >= len(self._states):
                return False
            self._index += 1
            return True
    """,
))

SPECS.append(spec(
    id="cal28",
    title="VersionedStore",
    difficulty="hard",
    objective="""
    class VersionedStore

    A key/value store that remembers every version. Versions are numbered from
    one and are shared across all keys: each write takes the next number.
    Support:

      set(key, value) — record the write and return its version number.

      get(key, version=None) — the value the key held as of that version,
      meaning the most recent write at or before it. Without a version, the
      newest value. A key with no write at or before that version raises
      KeyError, and a version number that has never been issued, or is below
      one, raises ValueError.

      keys(version=None) — the keys that existed as of that version, sorted.

    A value of None is an ordinary value and must not be confused with a key
    that was never written.
    """,
    holdout_test="""
    s = VersionedStore()
    assert s.keys() == []
    assert s.set('a', 1) == 1
    assert s.set('b', 2) == 2
    assert s.set('a', 3) == 3
    assert s.get('a') == 3
    assert s.get('a', 1) == 1
    assert s.get('a', 2) == 1
    assert s.get('b', 2) == 2
    assert s.keys() == ['a', 'b']
    assert s.keys(1) == ['a']
    assert s.set('c', None) == 4
    assert s.get('c') is None
    assert s.keys(4) == ['a', 'b', 'c']
    _bad = 0
    for _call in [lambda: s.get('b', 1), lambda: s.get('zz'),
                  lambda: s.get('a', 0), lambda: s.get('a', 9)]:
        try:
            _call()
        except (KeyError, ValueError):
            _bad += 1
    assert _bad == 4
    _kinds = []
    try:
        s.get('b', 1)
    except KeyError:
        _kinds.append('key')
    try:
        s.get('a', 99)
    except ValueError:
        _kinds.append('value')
    assert _kinds == ['key', 'value']
    """,
    reference="""
    class VersionedStore:
        def __init__(self):
            self._version = 0
            self._log = {}

        def set(self, key, value):
            self._version += 1
            self._log.setdefault(key, []).append((self._version, value))
            return self._version

        def get(self, key, version=None):
            if version is None:
                version = self._version
            if version < 1 or version > self._version:
                raise ValueError('no such version')
            found = False
            best = None
            for stamp, value in self._log.get(key, []):
                if stamp <= version:
                    best = value
                    found = True
            if not found:
                raise KeyError(key)
            return best

        def keys(self, version=None):
            if version is None:
                version = self._version
            out = []
            for key, entries in self._log.items():
                for stamp, value in entries:
                    if stamp <= version:
                        out.append(key)
                        break
            return sorted(out)
    """,
))

SPECS.append(spec(
    id="cal29",
    title="PriorityScheduler",
    difficulty="medium",
    objective="""
    class PriorityScheduler

    A queue that serves the most urgent job first, where a smaller priority
    number is more urgent. Support:

      add(name, priority) — enqueue a job. Names may repeat.

      pop() — remove and return the name of the most urgent job, or None when
      nothing is queued. Jobs of equal priority are served in the order they
      were added.

      cancel(name) — remove the job with that name that was added earliest,
      whatever its priority, and return True; return False if no job has that
      name.

      pending() — how many jobs are queued.
    """,
    holdout_test="""
    q = PriorityScheduler()
    assert q.pop() is None
    assert q.pending() == 0
    q.add('a', 2)
    q.add('b', 1)
    q.add('c', 2)
    assert q.pending() == 3
    assert q.pop() == 'b'
    assert q.pop() == 'a'
    assert q.pop() == 'c'
    assert q.pop() is None
    q.add('x', 5)
    q.add('y', 1)
    q.add('x', 0)
    assert q.cancel('x') is True
    assert q.pop() == 'x'
    assert q.pop() == 'y'
    assert q.cancel('nope') is False
    assert q.pending() == 0
    """,
    reference="""
    class PriorityScheduler:
        def __init__(self):
            self._items = []

        def add(self, name, priority):
            self._items.append((priority, name))

        def pop(self):
            if not self._items:
                return None
            best = None
            for index, item in enumerate(self._items):
                if best is None or item[0] < self._items[best][0]:
                    best = index
            return self._items.pop(best)[1]

        def cancel(self, name):
            for index, item in enumerate(self._items):
                if item[1] == name:
                    del self._items[index]
                    return True
            return False

        def pending(self):
            return len(self._items)
    """,
))

SPECS.append(spec(
    id="cal30",
    title="MinHeap",
    difficulty="medium",
    objective="""
    class MinHeap

    A smallest-first collection. The constructor takes an optional key
    function; without one the items compare directly. Support:

      push(item) — add an item.

      peek() — the smallest item, left in place.

      pop() — remove and return the smallest item. Items whose keys are equal
      come out in the order they were pushed.

      pop_all() — remove and return every item, smallest first, obeying the
      same tie rule.

      len(heap) — how many items are held.

    Taking from an empty heap raises IndexError. Items themselves are never
    compared when a key function is given.
    """,
    holdout_test="""
    h = MinHeap()
    assert len(h) == 0
    h.push(3)
    h.push(1)
    h.push(2)
    assert len(h) == 3
    assert h.peek() == 1
    assert len(h) == 3
    assert h.pop() == 1
    assert h.pop_all() == [2, 3]
    assert len(h) == 0
    k = MinHeap(key=len)
    k.push('ccc')
    k.push('d')
    k.push('a')
    k.push('bb')
    assert k.pop() == 'd'
    assert k.peek() == 'a'
    assert k.pop_all() == ['a', 'bb', 'ccc']
    _bad = 0
    for _call in [lambda: h.pop(), lambda: h.peek()]:
        try:
            _call()
        except IndexError:
            _bad += 1
    assert _bad == 2
    """,
    reference="""
    class MinHeap:
        def __init__(self, key=None):
            self._key = key
            self._items = []

        def _rank(self, item):
            return self._key(item) if self._key else item

        def _best(self):
            best = None
            for index, item in enumerate(self._items):
                if best is None or self._rank(item) < self._rank(self._items[best]):
                    best = index
            return best

        def push(self, item):
            self._items.append(item)

        def peek(self):
            if not self._items:
                raise IndexError('heap is empty')
            return self._items[self._best()]

        def pop(self):
            if not self._items:
                raise IndexError('heap is empty')
            return self._items.pop(self._best())

        def pop_all(self):
            out = []
            while self._items:
                out.append(self.pop())
            return out

        def __len__(self):
            return len(self._items)
    """,
))

SPECS.append(spec(
    id="cal31",
    title="UnionFind",
    difficulty="hard",
    objective="""
    class UnionFind

    Disjoint sets over hashable labels. A label is known once it has been
    passed to any method, and starts in a set of its own. Support:

      find(label) — the representative of the label's set, which is always the
      smallest label in that set.

      union(a, b) — merge the two sets, returning True, or False if they were
      already the same set.

      connected(a, b) — whether the two labels share a set.

      groups() — every set as a sorted list, the lists themselves sorted.
    """,
    holdout_test="""
    u = UnionFind()
    assert u.find('b') == 'b'
    assert u.connected('a', 'b') is False
    assert u.union('a', 'b') is True
    assert u.find('b') == 'a'
    assert u.find('a') == 'a'
    assert u.connected('a', 'b') is True
    assert u.union('a', 'b') is False
    assert u.union('c', 'd') is True
    assert u.union('b', 'd') is True
    assert u.find('d') == 'a'
    assert u.groups() == [['a', 'b', 'c', 'd']]
    v = UnionFind()
    v.union('z', 'y')
    v.union('m', 'n')
    assert v.find('z') == 'y'
    assert v.groups() == [['m', 'n'], ['y', 'z']]
    assert v.connected('m', 'z') is False
    """,
    reference="""
    class UnionFind:
        def __init__(self):
            self._parent = {}

        def find(self, label):
            if label not in self._parent:
                self._parent[label] = label
                return label
            root = label
            while self._parent[root] != root:
                root = self._parent[root]
            while self._parent[label] != root:
                self._parent[label], label = root, self._parent[label]
            return root

        def union(self, a, b):
            ra = self.find(a)
            rb = self.find(b)
            if ra == rb:
                return False
            if rb < ra:
                ra, rb = rb, ra
            self._parent[rb] = ra
            return True

        def connected(self, a, b):
            return self.find(a) == self.find(b)

        def groups(self):
            buckets = {}
            for label in list(self._parent):
                buckets.setdefault(self.find(label), []).append(label)
            return sorted(sorted(group) for group in buckets.values())
    """,
))

SPECS.append(spec(
    id="cal32",
    title="histogram",
    difficulty="hard",
    objective="""
    def histogram(pairs: list, width: int) -> list

    Render (label, value) pairs as lines of a text histogram, in the order
    given. Each line is the label converted to a string and padded on the LEFT
    with spaces to the width of the longest label, then a space, a vertical
    bar and a space, then the bar itself drawn with hash characters.

    The largest value in the data is exactly `width` hashes long and the
    others are scaled in proportion and rounded to the nearest whole hash,
    with a half rounding up. A value of zero draws nothing, so its line ends
    after the space that follows the bar character. When every value is zero
    no line has a bar.

    An empty input gives an empty list. A width that is not positive, or any
    negative value, raises ValueError.
    """,
    holdout_test="""
    assert histogram([], 4) == []
    assert histogram([('a', 1), ('bb', 2)], 4) == [' a | ##', 'bb | ####']
    assert histogram([('x', 0), ('y', 3)], 2) == ['x | ', 'y | ##']
    assert histogram([('a', 1), ('b', 3)], 3) == ['a | #', 'b | ###']
    assert histogram([('a', 1), ('b', 2)], 3) == ['a | ##', 'b | ###']
    assert histogram([('a', 0)], 5) == ['a | ']
    assert histogram([('a', 0), ('b', 0)], 5) == ['a | ', 'b | ']
    assert histogram([('long', 5), ('s', 5)], 1) == ['long | #', '   s | #']
    assert histogram([(12, 4)], 2) == ['12 | ##']
    _bad = 0
    for _call in [lambda: histogram([('a', 1)], 0), lambda: histogram([('a', -1)], 2)]:
        try:
            _call()
        except ValueError:
            _bad += 1
    assert _bad == 2
    """,
    reference="""
    def histogram(pairs, width):
        if width <= 0:
            raise ValueError('width must be positive')
        if not pairs:
            return []
        for name, value in pairs:
            if value < 0:
                raise ValueError('values must not be negative')
        label_width = max(len(str(name)) for name, value in pairs)
        top = max(value for name, value in pairs)
        out = []
        for name, value in pairs:
            length = 0 if top == 0 else (2 * value * width + top) // (2 * top)
            out.append(str(name).rjust(label_width) + ' | ' + '#' * length)
        return out
    """,
))

SPECS.append(spec(
    id="cal33",
    title="OrderedSet",
    difficulty="medium",
    objective="""
    class OrderedSet

    A set that remembers the order in which things were first added. The
    constructor takes an optional iterable of starting items, whose duplicates
    collapse to their first appearance. Support:

      add(item) — add it, returning True, or False if it was already there.

      discard(item) — remove it, returning True, or False if it was absent.

      contains(item) — whether it is present.

      items() — the items in order, as a list the caller may modify freely.

      index(item) — its position in that order, raising KeyError if absent.

      move_to_end(item) — send it to the end of the order, raising KeyError if
      absent.
    """,
    holdout_test="""
    s = OrderedSet()
    assert s.items() == []
    assert s.add('a') is True
    assert s.add('b') is True
    assert s.add('a') is False
    assert s.items() == ['a', 'b']
    assert s.contains('a') is True
    assert s.contains('z') is False
    assert s.index('b') == 1
    s.move_to_end('a')
    assert s.items() == ['b', 'a']
    assert s.index('a') == 1
    assert s.discard('b') is True
    assert s.discard('b') is False
    assert s.items() == ['a']
    t = OrderedSet(['x', 'y', 'x', 'z'])
    assert t.items() == ['x', 'y', 'z']
    _snapshot = t.items()
    _snapshot.append('q')
    assert t.items() == ['x', 'y', 'z']
    _bad = 0
    for _call in [lambda: t.index('nope'), lambda: t.move_to_end('nope')]:
        try:
            _call()
        except KeyError:
            _bad += 1
    assert _bad == 2
    """,
    reference="""
    class OrderedSet:
        def __init__(self, items=()):
            self._items = {}
            for item in items:
                self._items[item] = True

        def add(self, item):
            if item in self._items:
                return False
            self._items[item] = True
            return True

        def discard(self, item):
            if item not in self._items:
                return False
            del self._items[item]
            return True

        def contains(self, item):
            return item in self._items

        def items(self):
            return list(self._items)

        def index(self, item):
            if item not in self._items:
                raise KeyError(item)
            return self.items().index(item)

        def move_to_end(self, item):
            if item not in self._items:
                raise KeyError(item)
            del self._items[item]
            self._items[item] = True
    """,
))

SPECS.append(spec(
    id="cal34",
    title="critical_path",
    difficulty="hard",
    objective="""
    def critical_path(tasks: dict) -> tuple

    Each entry of tasks maps a name to a (duration, dependencies) pair, and a
    task may not start until all of its dependencies have finished. Return the
    earliest time by which everything can be finished, together with a chain
    of names that takes exactly that long, ordered from the first task to the
    last.

    Where several chains are equally long, the one whose names come first
    alphabetically at the earliest point of difference is reported. An empty
    set of tasks finishes at time zero with an empty chain.

    A dependency that is not a task, and any circular dependency, raise
    ValueError.
    """,
    holdout_test="""
    assert critical_path({}) == (0, [])
    assert critical_path({'a': (1, [])}) == (1, ['a'])
    assert critical_path({'a': (1, []), 'b': (1, [])}) == (1, ['a'])
    _chain = {'a': (3, []), 'b': (2, ['a']), 'c': (4, ['b'])}
    assert critical_path(_chain) == (9, ['a', 'b', 'c'])
    _diamond = {'a': (2, []), 'b': (3, ['a']), 'c': (1, ['a']), 'd': (1, ['b', 'c'])}
    assert critical_path(_diamond) == (6, ['a', 'b', 'd'])
    _tie = {'a': (1, []), 'b': (1, []), 'c': (1, ['a', 'b'])}
    assert critical_path(_tie) == (2, ['a', 'c'])
    assert critical_path({'a': (0, [])}) == (0, ['a'])
    _bad = 0
    for _tasks in [{'a': (1, ['z'])}, {'a': (1, ['b']), 'b': (1, ['a'])}, {'a': (1, ['a'])}]:
        try:
            critical_path(_tasks)
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def critical_path(tasks):
        finish = {}
        choice = {}
        visiting = set()

        def resolve(name):
            if name in finish:
                return finish[name]
            if name in visiting:
                raise ValueError('circular dependency')
            if name not in tasks:
                raise ValueError('unknown dependency')
            visiting.add(name)
            duration, deps = tasks[name]
            best = 0
            pick = None
            for dep in sorted(deps):
                value = resolve(dep)
                if value > best:
                    best = value
                    pick = dep
            visiting.discard(name)
            finish[name] = best + duration
            choice[name] = pick
            return finish[name]

        total = 0
        last = None
        for name in sorted(tasks):
            value = resolve(name)
            if value > total:
                total = value
                last = name
        if last is None and tasks:
            last = sorted(tasks)[0]
        path = []
        while last is not None:
            path.append(last)
            last = choice[last]
        path.reverse()
        return total, path
    """,
))

SPECS.append(spec(
    id="cal35",
    title="stable_topo_sort",
    difficulty="hard",
    objective="""
    def stable_topo_sort(graph: dict) -> list

    The graph maps a node to the list of nodes that must come after it. A node
    that appears only as a successor is still a node.

    Return an order in which every node comes before its successors and, among
    the nodes that are ready at any moment, the alphabetically smallest is
    taken first — so the result is the one order a careful reader would agree
    on rather than any valid order.

    A graph that cannot be ordered raises ValueError.
    """,
    holdout_test="""
    assert stable_topo_sort({}) == []
    assert stable_topo_sort({'a': []}) == ['a']
    assert stable_topo_sort({'a': ['b']}) == ['a', 'b']
    assert stable_topo_sort({'b': ['a']}) == ['b', 'a']
    assert stable_topo_sort({'c': [], 'a': [], 'b': []}) == ['a', 'b', 'c']
    assert stable_topo_sort({'a': ['c'], 'b': ['c'], 'c': []}) == ['a', 'b', 'c']
    assert stable_topo_sort({'z': ['a'], 'a': ['m']}) == ['z', 'a', 'm']
    _wide = {'a': ['b', 'c'], 'b': ['d'], 'c': ['d'], 'd': []}
    assert stable_topo_sort(_wide) == ['a', 'b', 'c', 'd']
    _bad = 0
    for _graph in [{'a': ['b'], 'b': ['a']}, {'a': ['a']}]:
        try:
            stable_topo_sort(_graph)
        except ValueError:
            _bad += 1
    assert _bad == 2
    """,
    reference="""
    def stable_topo_sort(graph):
        nodes = set(graph)
        for targets in graph.values():
            nodes.update(targets)
        indegree = {node: 0 for node in nodes}
        for source in graph:
            for target in graph[source]:
                indegree[target] += 1
        ready = sorted(node for node in nodes if indegree[node] == 0)
        out = []
        while ready:
            node = ready.pop(0)
            out.append(node)
            for target in sorted(graph.get(node, [])):
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
            ready.sort()
        if len(out) != len(nodes):
            raise ValueError('graph has a cycle')
        return out
    """,
))

SPECS.append(spec(
    id="cal36",
    title="find_cycle",
    difficulty="hard",
    objective="""
    def find_cycle(graph: dict) -> list

    The graph maps a node to the list of nodes it points at. Return one cycle
    as the list of nodes around it, each named once and starting at the node
    where the cycle closes, or an empty list when the graph has none.

    The search is deterministic: it starts from the alphabetically first node
    and always follows the alphabetically first successor it has not finished
    with, and the cycle reported is the first one it closes.
    """,
    holdout_test="""
    assert find_cycle({}) == []
    assert find_cycle({'a': []}) == []
    assert find_cycle({'a': ['b'], 'b': []}) == []
    assert find_cycle({'a': ['a']}) == ['a']
    assert find_cycle({'a': ['b'], 'b': ['a']}) == ['a', 'b']
    assert find_cycle({'b': ['a'], 'a': ['b']}) == ['a', 'b']
    assert find_cycle({'a': ['b', 'c'], 'b': [], 'c': ['a']}) == ['a', 'c']
    assert find_cycle({'a': ['b'], 'b': ['c'], 'c': ['b']}) == ['b', 'c']
    assert find_cycle({'a': ['b'], 'b': ['c'], 'c': []}) == []
    assert find_cycle({'x': ['y'], 'y': ['z'], 'z': ['x']}) == ['x', 'y', 'z']
    """,
    reference="""
    def find_cycle(graph):
        state = {}
        stack = []

        def visit(node):
            if state.get(node) == 2:
                return None
            if state.get(node) == 1:
                return stack[stack.index(node):]
            state[node] = 1
            stack.append(node)
            for target in sorted(graph.get(node, [])):
                found = visit(target)
                if found is not None:
                    return found
            stack.pop()
            state[node] = 2
            return None

        for node in sorted(graph):
            found = visit(node)
            if found is not None:
                return found
        return []
    """,
))

SPECS.append(spec(
    id="cal37",
    title="knapsack_items",
    difficulty="hard",
    objective="""
    def knapsack_items(items: list, capacity: int) -> tuple

    Each element of items is a (name, weight, value) triple and each may be
    taken once or left. Choose the selection of greatest total value whose
    total weight does not exceed capacity, and return that value together with
    the chosen names sorted alphabetically.

    Taking the items with the best value for their weight is not always the
    best selection. Where two selections tie on value, report the one whose
    sorted list of names is alphabetically smaller — which, in particular,
    prefers taking nothing over taking something worth nothing.

    A negative capacity raises ValueError.
    """,
    holdout_test="""
    assert knapsack_items([], 10) == (0, [])
    assert knapsack_items([('a', 5, 10)], 4) == (0, [])
    assert knapsack_items([('a', 5, 10)], 5) == (10, ['a'])
    _greedy = [('a', 10, 60), ('b', 20, 100), ('c', 30, 120)]
    assert knapsack_items(_greedy, 50) == (220, ['b', 'c'])
    _trap = [('big', 6, 7), ('x', 3, 4), ('y', 3, 4)]
    assert knapsack_items(_trap, 6) == (8, ['x', 'y'])
    assert knapsack_items([('a', 1, 5), ('b', 1, 5)], 2) == (10, ['a', 'b'])
    assert knapsack_items([('a', 1, 0)], 5) == (0, [])
    assert knapsack_items([('a', 0, 3)], 0) == (3, ['a'])
    assert knapsack_items([('z', 2, 3), ('a', 2, 3)], 2) == (3, ['a'])
    _err = False
    try:
        knapsack_items([], -1)
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def knapsack_items(items, capacity):
        if capacity < 0:
            raise ValueError('capacity must not be negative')
        table = {0: (0, [])}
        for name, weight, value in items:
            updates = {}
            for used in sorted(table):
                total, chosen = table[used]
                room = used + weight
                if room > capacity:
                    continue
                candidate = (total + value, sorted(chosen + [name]))
                current = updates.get(room, table.get(room))
                if current is None or candidate[0] > current[0] or (
                        candidate[0] == current[0] and candidate[1] < current[1]):
                    updates[room] = candidate
            table.update(updates)
        best = (0, [])
        for used in sorted(table):
            entry = table[used]
            if entry[0] > best[0] or (entry[0] == best[0] and entry[1] < best[1]):
                best = entry
        return best
    """,
))

SPECS.append(spec(
    id="cal38",
    title="coin_change_ways",
    difficulty="hard",
    objective="""
    def coin_change_ways(coins: list, amount: int) -> int

    Count the ways to make exactly `amount` from an unlimited supply of the
    given coin values. Two ways differ only by which coins they use and how
    many of each: paying with a five then a two is the same way as paying with
    a two then a five, and must be counted once.

    A repeated coin value in the argument adds nothing. There is exactly one
    way to make zero. A negative amount, or a coin value that is not positive,
    raises ValueError.
    """,
    holdout_test="""
    assert coin_change_ways([1, 2, 5], 0) == 1
    assert coin_change_ways([], 0) == 1
    assert coin_change_ways([], 3) == 0
    assert coin_change_ways([2], 3) == 0
    assert coin_change_ways([1, 2], 3) == 2
    assert coin_change_ways([1, 2, 5], 5) == 4
    assert coin_change_ways([2, 5, 3, 6], 10) == 5
    assert coin_change_ways([1, 1, 2], 3) == 2
    assert coin_change_ways([3], 9) == 1
    assert coin_change_ways([5, 10, 25], 30) == 5
    _bad = 0
    for _call in [lambda: coin_change_ways([1], -1), lambda: coin_change_ways([0], 5),
                  lambda: coin_change_ways([-2], 4)]:
        try:
            _call()
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def coin_change_ways(coins, amount):
        if amount < 0:
            raise ValueError('amount must not be negative')
        ways = [0] * (amount + 1)
        ways[0] = 1
        for coin in sorted(set(coins)):
            if coin <= 0:
                raise ValueError('coins must be positive')
            for value in range(coin, amount + 1):
                ways[value] += ways[value - coin]
        return ways[amount]
    """,
))

SPECS.append(spec(
    id="cal39",
    title="longest_common_substring",
    difficulty="medium",
    objective="""
    def longest_common_substring(a: str, b: str) -> str

    Return the longest run of consecutive characters that appears in both
    strings. Where several runs tie for longest, return the one that ends
    earliest in the first argument, and among those the one that ends earliest
    in the second.

    A run of characters that appears in both but not consecutively does not
    count. When the strings share nothing the answer is the empty string.
    """,
    holdout_test="""
    assert longest_common_substring('', 'abc') == ''
    assert longest_common_substring('abc', '') == ''
    assert longest_common_substring('abc', 'xyz') == ''
    assert longest_common_substring('abcdef', 'zabcy') == 'abc'
    assert longest_common_substring('abcdef', 'abcdef') == 'abcdef'
    assert longest_common_substring('ab', 'ba') == 'a'
    assert longest_common_substring('xxabxx', 'yyabyy') == 'ab'
    assert longest_common_substring('ace', 'abcde') == 'a'
    assert longest_common_substring('banana', 'ananas') == 'anana'
    assert longest_common_substring('aaa', 'aa') == 'aa'
    """,
    reference="""
    def longest_common_substring(a, b):
        best = ''
        table = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                if a[i - 1] == b[j - 1]:
                    table[i][j] = table[i - 1][j - 1] + 1
                    if table[i][j] > len(best):
                        best = a[i - table[i][j]:i]
        return best
    """,
))

SPECS.append(spec(
    id="cal40",
    title="diff_unified",
    difficulty="hard",
    objective="""
    def diff_unified(a: list, b: list) -> list

    Compare two lists of lines and return the edit script that turns the first
    into the second, as one string per step: a line kept by both is prefixed
    with a space, a line only in the first is prefixed with a minus, and a
    line only in the second is prefixed with a plus.

    The script must keep as many lines as possible rather than deleting
    everything and adding it back. Where a choice remains, the deletion is
    emitted before the insertion, and the earliest possible deletion is
    preferred.
    """,
    holdout_test="""
    assert diff_unified([], []) == []
    assert diff_unified(['a'], ['a']) == [' a']
    assert diff_unified([], ['a']) == ['+a']
    assert diff_unified(['a'], []) == ['-a']
    assert diff_unified(['a', 'b'], ['a', 'c']) == [' a', '-b', '+c']
    assert diff_unified(['a', 'b', 'c'], ['a', 'c']) == [' a', '-b', ' c']
    assert diff_unified(['a', 'c'], ['a', 'b', 'c']) == [' a', '+b', ' c']
    assert diff_unified(['x'], ['y']) == ['-x', '+y']
    assert diff_unified(['a', 'b'], ['b', 'a']) == ['-a', ' b', '+a']
    assert diff_unified(['a', 'b', 'c'], ['c', 'b', 'a']) == ['-a', '-b', ' c', '+b', '+a']
    assert diff_unified(['a', 'b', 'c', 'd'], ['b', 'd', 'e']) == ['-a', ' b', '-c', ' d', '+e']
    assert diff_unified(['x', 'a', 'b', 'y'], ['a', 'b']) == ['-x', ' a', ' b', '-y']
    assert diff_unified(['1', '2', '3', '4', '5'], ['2', '4', '6']) == [
        '-1', ' 2', '-3', ' 4', '-5', '+6']
    assert diff_unified(['p', 'q', 'r'], ['q', 'p', 'r']) == ['-p', ' q', '+p', ' r']
    assert diff_unified(['c', 'a', 'a', 'b'], ['b', 'c', 'c']) == [
        '-c', '-a', '-a', ' b', '+c', '+c']
    assert diff_unified(['b', 'b', 'c', 'b'], ['c', 'b', 'c', 'b']) == [
        '-b', '+c', ' b', ' c', ' b']
    """,
    reference="""
    def diff_unified(a, b):
        n = len(a)
        m = len(b)
        table = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(n - 1, -1, -1):
            for j in range(m - 1, -1, -1):
                if a[i] == b[j]:
                    table[i][j] = table[i + 1][j + 1] + 1
                else:
                    table[i][j] = max(table[i + 1][j], table[i][j + 1])
        out = []
        i = 0
        j = 0
        while i < n and j < m:
            if a[i] == b[j]:
                out.append(' ' + a[i])
                i += 1
                j += 1
            elif table[i + 1][j] >= table[i][j + 1]:
                out.append('-' + a[i])
                i += 1
            else:
                out.append('+' + b[j])
                j += 1
        while i < n:
            out.append('-' + a[i])
            i += 1
        while j < m:
            out.append('+' + b[j])
            j += 1
        return out
    """,
))

SPECS.append(spec(
    id="cal41",
    title="apply_line_patch",
    difficulty="medium",
    objective="""
    def apply_line_patch(lines: list, patch: list) -> list

    The patch is a list of steps in the same shape an edit script has: a step
    beginning with a space keeps the line that follows it, one beginning with
    a minus removes it, and one beginning with a plus inserts it. Apply the
    patch to lines and return the resulting list. The argument is not
    modified.

    The patch must describe the whole of lines, in order: a kept or removed
    step whose text is not the line it lands on, a patch that runs out before
    the lines do, an empty step, and a step with any other marker all raise
    ValueError.
    """,
    holdout_test="""
    assert apply_line_patch([], []) == []
    assert apply_line_patch(['a'], [' a']) == ['a']
    assert apply_line_patch(['a'], ['-a']) == []
    assert apply_line_patch([], ['+a']) == ['a']
    assert apply_line_patch(['a', 'b'], [' a', '-b', '+c']) == ['a', 'c']
    assert apply_line_patch(['a', 'c'], [' a', '+b', ' c']) == ['a', 'b', 'c']
    _src = ['a']
    assert apply_line_patch(_src, ['-a', '+z']) == ['z']
    assert _src == ['a']
    _bad = 0
    for _patch in [[' x'], [], ['*a'], [''], [' a', ' b']]:
        try:
            apply_line_patch(['a'], _patch)
        except ValueError:
            _bad += 1
    assert _bad == 5
    """,
    reference="""
    def apply_line_patch(lines, patch):
        out = []
        index = 0
        for entry in patch:
            if not entry:
                raise ValueError('empty patch step')
            mark = entry[0]
            text = entry[1:]
            if mark == '+':
                out.append(text)
                continue
            if mark != ' ' and mark != '-':
                raise ValueError('bad marker')
            if index >= len(lines) or lines[index] != text:
                raise ValueError('patch does not apply')
            if mark == ' ':
                out.append(text)
            index += 1
        if index != len(lines):
            raise ValueError('patch does not cover every line')
        return out
    """,
))

SPECS.append(spec(
    id="cal42",
    title="simplify_fraction",
    difficulty="medium",
    objective="""
    def simplify_fraction(n: int, d: int) -> tuple

    Reduce the fraction n over d to lowest terms and return it as a
    (numerator, denominator) pair. The denominator of the result is always
    positive, so a negative sign always ends up on the numerator, and a zero
    numerator is reported over one.

    A zero denominator raises ZeroDivisionError.
    """,
    holdout_test="""
    assert simplify_fraction(1, 2) == (1, 2)
    assert simplify_fraction(2, 4) == (1, 2)
    assert simplify_fraction(-2, 4) == (-1, 2)
    assert simplify_fraction(2, -4) == (-1, 2)
    assert simplify_fraction(-2, -4) == (1, 2)
    assert simplify_fraction(0, 5) == (0, 1)
    assert simplify_fraction(0, -5) == (0, 1)
    assert simplify_fraction(6, 3) == (2, 1)
    assert simplify_fraction(-6, 3) == (-2, 1)
    assert simplify_fraction(7, 13) == (7, 13)
    assert simplify_fraction(120, 90) == (4, 3)
    assert simplify_fraction(3, -1) == (-3, 1)
    assert simplify_fraction(-1, 2) == (-1, 2)
    assert simplify_fraction(-3, -1) == (3, 1)
    _err = False
    try:
        simplify_fraction(1, 0)
    except ZeroDivisionError:
        _err = True
    assert _err is True
    """,
    reference="""
    def simplify_fraction(n, d):
        if d == 0:
            raise ZeroDivisionError('denominator must not be zero')
        if n == 0:
            return (0, 1)
        a = abs(n)
        b = abs(d)
        while b:
            a, b = b, a % b
        sign = -1 if (n < 0) != (d < 0) else 1
        return (sign * (abs(n) // a), abs(d) // a)
    """,
))

SPECS.append(spec(
    id="cal43",
    title="eval_boolean",
    difficulty="hard",
    objective="""
    def eval_boolean(expr: str, values: dict) -> bool

    Evaluate a boolean expression written with names, the words and, or and
    not, and parentheses. Spaces are insignificant. A name stands for the
    truth of its entry in values.

    The word not binds tightest, then and, then or, so an expression mixing
    them means what a Python programmer would expect. The result is a real
    boolean.

    A name with no entry in values raises KeyError. A malformed expression —
    an unbalanced parenthesis, a missing operand, a stray character, anything
    left over at the end — raises ValueError.
    """,
    holdout_test="""
    _v = {'a': True, 'b': False, 'c': True}
    assert eval_boolean('a', _v) is True
    assert eval_boolean('b', _v) is False
    assert eval_boolean('not a', _v) is False
    assert eval_boolean('not not b', _v) is False
    assert eval_boolean('a and b', _v) is False
    assert eval_boolean('a or b', _v) is True
    assert eval_boolean('a or b and b', _v) is True
    assert eval_boolean('(a or b) and b', _v) is False
    assert eval_boolean('not a or c', _v) is True
    assert eval_boolean('not (a or c)', _v) is False
    assert eval_boolean('  a   and   c  ', _v) is True
    _missing = None
    try:
        eval_boolean('a and zz', _v)
    except KeyError as exc:
        _missing = exc.args[0]
    assert _missing == 'zz'
    _bad = 0
    for _text in ['', '(a', 'a)', 'a and', 'and a', 'a $ b', 'a b']:
        try:
            eval_boolean(_text, _v)
        except ValueError:
            _bad += 1
    assert _bad == 7
    """,
    reference="""
    def eval_boolean(expr, values):
        tokens = []
        i = 0
        while i < len(expr):
            ch = expr[i]
            if ch.isspace():
                i += 1
                continue
            if ch == '(' or ch == ')':
                tokens.append(ch)
                i += 1
                continue
            if ch.isalnum() or ch == '_':
                start = i
                while i < len(expr) and (expr[i].isalnum() or expr[i] == '_'):
                    i += 1
                tokens.append(expr[start:i])
                continue
            raise ValueError('bad character')
        state = {'pos': 0}

        def peek():
            return tokens[state['pos']] if state['pos'] < len(tokens) else None

        def take():
            token = peek()
            state['pos'] += 1
            return token

        def primary():
            token = take()
            if token is None:
                raise ValueError('unexpected end of expression')
            if token == 'not':
                return not primary()
            if token == '(':
                value = expression()
                if take() != ')':
                    raise ValueError('missing closing parenthesis')
                return value
            if token == ')':
                raise ValueError('unexpected closing parenthesis')
            if token == 'and' or token == 'or':
                raise ValueError('operator without an operand')
            if token not in values:
                raise KeyError(token)
            return bool(values[token])

        def conjunction():
            value = primary()
            while peek() == 'and':
                take()
                value = primary() and value
            return value

        def expression():
            value = conjunction()
            while peek() == 'or':
                take()
                value = conjunction() or value
            return value

        result = expression()
        if state['pos'] != len(tokens):
            raise ValueError('trailing tokens')
        return result
    """,
))

SPECS.append(spec(
    id="cal44",
    title="to_postfix",
    difficulty="hard",
    objective="""
    def to_postfix(expr: str) -> list

    Rewrite an arithmetic expression in postfix order, returning the tokens as
    a list of strings. The expression holds non-negative whole numbers, the
    four operators for addition, subtraction, multiplication and division, and
    parentheses; spaces are insignificant and a number may have several
    digits.

    Multiplication and division bind tighter than addition and subtraction,
    and operators of equal binding are applied left to right.

    An unbalanced parenthesis or any other character raises ValueError.
    """,
    holdout_test="""
    assert to_postfix('1') == ['1']
    assert to_postfix('12') == ['12']
    assert to_postfix('1+2') == ['1', '2', '+']
    assert to_postfix('1 + 2 * 3') == ['1', '2', '3', '*', '+']
    assert to_postfix('(1 + 2) * 3') == ['1', '2', '+', '3', '*']
    assert to_postfix('1 - 2 - 3') == ['1', '2', '-', '3', '-']
    assert to_postfix('1 - 2 + 3') == ['1', '2', '-', '3', '+']
    assert to_postfix('8 / 4 / 2') == ['8', '4', '/', '2', '/']
    assert to_postfix('2 * (3 + 4) / 5') == ['2', '3', '4', '+', '*', '5', '/']
    assert to_postfix('((7))') == ['7']
    _bad = 0
    for _text in ['(1', '1)', '1 $ 2']:
        try:
            to_postfix(_text)
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def to_postfix(expr):
        precedence = {'+': 1, '-': 1, '*': 2, '/': 2}
        out = []
        stack = []
        i = 0
        while i < len(expr):
            ch = expr[i]
            if ch.isspace():
                i += 1
                continue
            if ch.isdigit():
                start = i
                while i < len(expr) and expr[i].isdigit():
                    i += 1
                out.append(expr[start:i])
                continue
            if ch == '(':
                stack.append(ch)
            elif ch == ')':
                while stack and stack[-1] != '(':
                    out.append(stack.pop())
                if not stack:
                    raise ValueError('unbalanced parenthesis')
                stack.pop()
            elif ch in precedence:
                while stack and stack[-1] != '(' and precedence[stack[-1]] >= precedence[ch]:
                    out.append(stack.pop())
                stack.append(ch)
            else:
                raise ValueError('bad character')
            i += 1
        while stack:
            token = stack.pop()
            if token == '(':
                raise ValueError('unbalanced parenthesis')
            out.append(token)
        return out
    """,
))

SPECS.append(spec(
    id="cal45",
    title="matrix_determinant",
    difficulty="hard",
    objective="""
    def matrix_determinant(matrix: list) -> int

    Return the determinant of a square matrix of whole numbers, itself a whole
    number: the arithmetic must stay exact, so an answer arrived at through
    floating point division is not acceptable. The determinant of a matrix
    with no rows is one.

    A matrix whose rows are not all as long as the matrix is tall raises
    ValueError.
    """,
    holdout_test="""
    assert matrix_determinant([]) == 1
    assert matrix_determinant([[7]]) == 7
    assert matrix_determinant([[1, 2], [3, 4]]) == -2
    assert matrix_determinant([[0, 1], [1, 0]]) == -1
    assert matrix_determinant([[1, 0], [0, 1]]) == 1
    assert matrix_determinant([[2, 0, 0], [0, 3, 0], [0, 0, 4]]) == 24
    assert matrix_determinant([[1, 2, 3], [4, 5, 6], [7, 8, 10]]) == -3
    assert matrix_determinant([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == 0
    assert matrix_determinant([[0, 0], [0, 0]]) == 0
    assert matrix_determinant([[0, 1, 0], [0, 2, 0], [0, 3, 0]]) == 0
    assert matrix_determinant([[0, 2], [3, 0]]) == -6
    _big = [[3, 1, 4, 1], [5, 9, 2, 6], [5, 3, 5, 8], [9, 7, 9, 3]]
    assert matrix_determinant(_big) == 98
    assert isinstance(matrix_determinant([[1, 2], [3, 4]]), int)
    _err = False
    try:
        matrix_determinant([[1, 2], [3]])
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def matrix_determinant(matrix):
        size = len(matrix)
        for row in matrix:
            if len(row) != size:
                raise ValueError('matrix must be square')
        if size == 0:
            return 1
        work = [list(row) for row in matrix]
        sign = 1
        previous = 1
        for k in range(size - 1):
            if work[k][k] == 0:
                swap = None
                for r in range(k + 1, size):
                    if work[r][k] != 0:
                        swap = r
                        break
                if swap is None:
                    return 0
                work[k], work[swap] = work[swap], work[k]
                sign = -sign
            for i in range(k + 1, size):
                for j in range(k + 1, size):
                    work[i][j] = (work[i][j] * work[k][k] - work[i][k] * work[k][j]) // previous
            previous = work[k][k]
        return sign * work[size - 1][size - 1]
    """,
))

SPECS.append(spec(
    id="cal46",
    title="encode_varint",
    difficulty="hard",
    objective="""
    def encode_varint(n: int) -> bytes
    def decode_varint(data: bytes, offset: int = 0) -> tuple

    Write both. A varint stores a non-negative whole number seven bits at a
    time, least significant group first, in as few bytes as possible. Every
    byte carries seven bits of the number in its lower half, and its top bit
    is set on all but the last byte to say that more follow. Zero takes one
    byte.

    decode_varint reads one varint starting at offset and returns the value
    together with the offset just past it, so several varints can be read from
    one buffer in turn.

    A negative number raises ValueError, and so does data that ends in the
    middle of a varint.
    """,
    holdout_test="""
    assert encode_varint(0) == b'\\x00'
    assert encode_varint(1) == b'\\x01'
    assert encode_varint(127) == b'\\x7f'
    assert encode_varint(128) == b'\\x80\\x01'
    assert encode_varint(300) == b'\\xac\\x02'
    assert encode_varint(16384) == b'\\x80\\x80\\x01'
    assert decode_varint(b'\\x00') == (0, 1)
    assert decode_varint(b'\\xac\\x02') == (300, 2)
    assert decode_varint(b'\\x01\\xac\\x02', 1) == (300, 3)
    assert all(decode_varint(encode_varint(_n)) == (_n, len(encode_varint(_n)))
               for _n in [0, 1, 63, 64, 127, 128, 255, 300, 16383, 16384, 999999])
    _bad = 0
    for _call in [lambda: encode_varint(-1), lambda: decode_varint(b''),
                  lambda: decode_varint(b'\\x80')]:
        try:
            _call()
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def encode_varint(n):
        if n < 0:
            raise ValueError('n must not be negative')
        out = bytearray()
        while True:
            part = n & 127
            n >>= 7
            if n:
                out.append(part | 128)
            else:
                out.append(part)
                break
        return bytes(out)

    def decode_varint(data, offset=0):
        value = 0
        shift = 0
        index = offset
        while True:
            if index >= len(data):
                raise ValueError('truncated varint')
            byte = data[index]
            value |= (byte & 127) << shift
            index += 1
            if byte < 128:
                return (value, index)
            shift += 7
    """,
))

SPECS.append(spec(
    id="cal47",
    title="base32_encode",
    difficulty="hard",
    objective="""
    def base32_encode(data: bytes) -> str

    Encode bytes in standard base32: the input is taken five bytes at a time,
    those forty bits are split into eight groups of five, and each group
    indexes the alphabet of the twenty-six uppercase letters followed by the
    digits two to seven.

    A final short group is padded with zero bits on the right to fill the last
    symbol it needs, and the output is then padded with equals signs so that
    every block is eight characters long. Empty input encodes to the empty
    string.
    """,
    holdout_test="""
    assert base32_encode(b'') == ''
    assert base32_encode(b'f') == 'MY======'
    assert base32_encode(b'fo') == 'MZXQ===='
    assert base32_encode(b'foo') == 'MZXW6==='
    assert base32_encode(b'foob') == 'MZXW6YQ='
    assert base32_encode(b'fooba') == 'MZXW6YTB'
    assert base32_encode(b'foobar') == 'MZXW6YTBOI======'
    assert base32_encode(b'\\x00') == 'AA======'
    assert base32_encode(b'\\xff') == '74======'
    assert base32_encode(b'\\x00\\x00\\x00\\x00\\x00') == 'AAAAAAAA'
    assert len(base32_encode(b'12345678')) == 16
    """,
    reference="""
    def base32_encode(data):
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
        out = []
        for start in range(0, len(data), 5):
            chunk = data[start:start + 5]
            bits = 0
            for byte in chunk:
                bits = (bits << 8) | byte
            bits = bits << ((5 - len(chunk)) * 8)
            symbols = (len(chunk) * 8 + 4) // 5
            for i in range(8):
                if i < symbols:
                    out.append(alphabet[(bits >> (35 - 5 * i)) & 31])
                else:
                    out.append('=')
        return ''.join(out)
    """,
))

SPECS.append(spec(
    id="cal48",
    title="sudoku_valid",
    difficulty="medium",
    objective="""
    def sudoku_valid(board: list) -> bool

    The board is nine rows of nine whole numbers, where zero means an empty
    cell. Report whether what has been filled in so far breaks no rule: no
    digit appears twice in a row, twice in a column, or twice in one of the
    nine three-by-three blocks. Empty cells never conflict, and the board need
    not be finished or solvable.

    A board that is not nine by nine, or that holds a number outside zero to
    nine, raises ValueError.
    """,
    holdout_test="""
    _blank = [[0] * 9 for _ in range(9)]
    assert sudoku_valid(_blank) is True
    _row = [list(r) for r in _blank]
    _row[0][0] = 5
    _row[0][8] = 5
    assert sudoku_valid(_row) is False
    _col = [list(r) for r in _blank]
    _col[0][3] = 7
    _col[8][3] = 7
    assert sudoku_valid(_col) is False
    _box = [list(r) for r in _blank]
    _box[0][0] = 4
    _box[2][2] = 4
    assert sudoku_valid(_box) is False
    _ok = [list(r) for r in _blank]
    _ok[0][0] = 4
    _ok[3][3] = 4
    _ok[6][6] = 4
    assert sudoku_valid(_ok) is True
    _full = [[(3 * (r % 3) + r // 3 + c) % 9 + 1 for c in range(9)] for r in range(9)]
    assert sudoku_valid(_full) is True
    _broken = [list(r) for r in _full]
    _broken[0][0] = _broken[0][1]
    assert sudoku_valid(_broken) is False
    _bad = 0
    for _board in [_blank[:8], [[0] * 8 for _ in range(9)],
                   [[10] + [0] * 8] + [[0] * 9 for _ in range(8)]]:
        try:
            sudoku_valid(_board)
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def sudoku_valid(board):
        if len(board) != 9:
            raise ValueError('board must have nine rows')
        for row in board:
            if len(row) != 9:
                raise ValueError('every row must have nine cells')
            for value in row:
                if value < 0 or value > 9:
                    raise ValueError('cell out of range')
        for i in range(9):
            rows = set()
            cols = set()
            boxes = set()
            for j in range(9):
                a = board[i][j]
                if a and a in rows:
                    return False
                rows.add(a)
                b = board[j][i]
                if b and b in cols:
                    return False
                cols.add(b)
                c = board[3 * (i // 3) + j // 3][3 * (i % 3) + j % 3]
                if c and c in boxes:
                    return False
                boxes.add(c)
        return True
    """,
))

SPECS.append(spec(
    id="cal49",
    title="diagonal_order",
    difficulty="medium",
    objective="""
    def diagonal_order(matrix: list) -> list

    Read a rectangular matrix along its anti-diagonals, alternating direction:
    the first diagonal is read upwards, the next downwards, and so on, so the
    walk zigzags from the top-left corner to the bottom-right one.

    An empty matrix reads as an empty list, and rows of unequal length raise
    ValueError.
    """,
    holdout_test="""
    assert diagonal_order([]) == []
    assert diagonal_order([[1]]) == [1]
    assert diagonal_order([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == [1, 2, 4, 7, 5, 3, 6, 8, 9]
    assert diagonal_order([[1, 2], [3, 4]]) == [1, 2, 3, 4]
    assert diagonal_order([[1, 2, 3]]) == [1, 2, 3]
    assert diagonal_order([[1], [2], [3]]) == [1, 2, 3]
    assert diagonal_order([[1, 2], [3, 4], [5, 6]]) == [1, 2, 3, 5, 4, 6]
    assert diagonal_order([[1, 2, 3], [4, 5, 6]]) == [1, 2, 4, 5, 3, 6]
    _err = False
    try:
        diagonal_order([[1, 2], [3]])
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def diagonal_order(matrix):
        if not matrix:
            return []
        width = len(matrix[0])
        for row in matrix:
            if len(row) != width:
                raise ValueError('rows must be the same length')
        out = []
        for d in range(len(matrix) + width - 1):
            items = []
            for i in range(len(matrix)):
                j = d - i
                if 0 <= j < width:
                    items.append(matrix[i][j])
            if d % 2 == 0:
                items.reverse()
            out.extend(items)
        return out
    """,
))

SPECS.append(spec(
    id="cal50",
    title="largest_region",
    difficulty="medium",
    objective="""
    def largest_region(grid: list) -> int

    Each element of grid is a string of equal length forming one row of a map.
    A region is a group of cells holding the same letter, joined to each other
    through shared edges rather than corners. A dot is empty ground and is
    never part of a region.

    Return the number of cells in the largest region, or zero when the map
    holds none. Rows of unequal length raise ValueError.
    """,
    holdout_test="""
    assert largest_region([]) == 0
    assert largest_region(['...']) == 0
    assert largest_region(['a']) == 1
    assert largest_region(['aa', 'aa']) == 4
    assert largest_region(['ab', 'ba']) == 1
    assert largest_region(['aa.', '.aa']) == 4
    assert largest_region(['a.a', 'a.a', 'aaa']) == 7
    assert largest_region(['ab', 'ab']) == 2
    assert largest_region(['a.b', 'a.b', 'a.b']) == 3
    assert largest_region(['abba', 'abba']) == 4
    assert largest_region(['aba']) == 1
    assert largest_region(['a.a.a']) == 1
    assert largest_region(['..a']) == 1
    assert largest_region(['..', '.a']) == 1
    _err = False
    try:
        largest_region(['ab', 'a'])
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def largest_region(grid):
        if not grid:
            return 0
        width = len(grid[0])
        for row in grid:
            if len(row) != width:
                raise ValueError('rows must be the same length')
        seen = set()
        best = 0
        for r in range(len(grid)):
            for c in range(width):
                if grid[r][c] == '.' or (r, c) in seen:
                    continue
                letter = grid[r][c]
                stack = [(r, c)]
                seen.add((r, c))
                size = 0
                while stack:
                    y, x = stack.pop()
                    size += 1
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny = y + dy
                        nx = x + dx
                        if 0 <= ny < len(grid) and 0 <= nx < width:
                            if (ny, nx) not in seen and grid[ny][nx] == letter:
                                seen.add((ny, nx))
                                stack.append((ny, nx))
                best = max(best, size)
        return best
    """,
))

SPECS.append(spec(
    id="cal51",
    title="escape_maze",
    difficulty="medium",
    objective="""
    def escape_maze(grid: list) -> int

    Each element of grid is a string forming one row of a maze, where a hash
    is a wall, a dot is open, S is where you start and E is the way out. You
    may step to a cell that shares an edge with the one you are on.

    Return the fewest steps from S to E, or minus one when there is no way
    through. A maze without exactly one S and one E, or with rows of unequal
    length, raises ValueError.
    """,
    holdout_test="""
    assert escape_maze(['SE']) == 1
    assert escape_maze(['S.E']) == 2
    assert escape_maze(['S#E']) == -1
    assert escape_maze(['S.', '.E']) == 2
    assert escape_maze(['S#', '.E']) == 2
    assert escape_maze(['S..', '##.', 'E..']) == 6
    assert escape_maze(['S....', '####.', 'E....']) == 10
    assert escape_maze(['S', '#', 'E']) == -1
    assert escape_maze(['S.#', '.#E', '...']) == 5
    _bad = 0
    for _maze in [['SS.E'], ['S..'], ['..E'], ['SE', 'E']]:
        try:
            escape_maze(_maze)
        except ValueError:
            _bad += 1
    assert _bad == 4
    """,
    reference="""
    def escape_maze(grid):
        width = len(grid[0]) if grid else 0
        start = None
        goal = None
        for r, row in enumerate(grid):
            if len(row) != width:
                raise ValueError('rows must be the same length')
            for c, cell in enumerate(row):
                if cell == 'S':
                    if start is not None:
                        raise ValueError('more than one start')
                    start = (r, c)
                elif cell == 'E':
                    if goal is not None:
                        raise ValueError('more than one exit')
                    goal = (r, c)
        if start is None or goal is None:
            raise ValueError('maze needs a start and an exit')
        queue = [(start, 0)]
        seen = {start}
        head = 0
        while head < len(queue):
            (y, x), steps = queue[head]
            head += 1
            if (y, x) == goal:
                return steps
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny = y + dy
                nx = x + dx
                if 0 <= ny < len(grid) and 0 <= nx < width:
                    if (ny, nx) not in seen and grid[ny][nx] != '#':
                        seen.add((ny, nx))
                        queue.append(((ny, nx), steps + 1))
        return -1
    """,
))

SPECS.append(spec(
    id="cal52",
    title="assign_rooms",
    difficulty="hard",
    objective="""
    def assign_rooms(meetings: list) -> list

    Each meeting is a [from, to] pair covering a half-open span of time, so a
    room freed at exactly the moment another meeting starts can be reused.
    Rooms are numbered from zero and opened only when needed.

    Consider the meetings in order of their start, breaking a tie by the
    earlier finish and then by their position in the argument, and give each
    the lowest-numbered room that is free when it starts. Return the room
    number given to each meeting, in the order the meetings were supplied.

    A meeting that does not end after it starts raises ValueError.
    """,
    holdout_test="""
    assert assign_rooms([]) == []
    assert assign_rooms([[0, 1]]) == [0]
    assert assign_rooms([[0, 5], [1, 2]]) == [0, 1]
    assert assign_rooms([[0, 1], [1, 2]]) == [0, 0]
    assert assign_rooms([[1, 2], [0, 1]]) == [0, 0]
    assert assign_rooms([[0, 10], [1, 3], [2, 4]]) == [0, 1, 2]
    assert assign_rooms([[0, 10], [1, 3], [4, 6]]) == [0, 1, 1]
    assert assign_rooms([[5, 6], [0, 1], [0, 2]]) == [0, 0, 1]
    assert assign_rooms([[0, 2], [0, 1], [1, 3]]) == [1, 0, 0]
    _err = False
    try:
        assign_rooms([[2, 2]])
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def assign_rooms(meetings):
        for span in meetings:
            if span[1] <= span[0]:
                raise ValueError('a meeting must end after it starts')
        order = sorted(range(len(meetings)),
                       key=lambda i: (meetings[i][0], meetings[i][1], i))
        free_at = []
        result = [0] * len(meetings)
        for index in order:
            start = meetings[index][0]
            end = meetings[index][1]
            room = None
            for r in range(len(free_at)):
                if free_at[r] <= start:
                    room = r
                    break
            if room is None:
                free_at.append(end)
                room = len(free_at) - 1
            else:
                free_at[room] = end
            result[index] = room
        return result
    """,
))

SPECS.append(spec(
    id="cal53",
    title="format_invoice",
    difficulty="hard",
    objective="""
    def format_invoice(items: list) -> list

    Each item is a (description, quantity, unit price in whole pence) triple.
    Return one line per item followed by a total line.

    An item line is the description padded on the right with spaces to the
    width of the longest description, then a space, a lowercase x, a space,
    the quantity, a space, an at sign, a space, the unit price, a space, an
    equals sign, a space, and the line total. The total line is the word TOTAL
    in capitals, a space, an equals sign, a space, and the sum of the line
    totals; it is present even when there are no items.

    Money is written as a pound sign, the whole pounds, a full stop and
    exactly two digits of pence. A negative quantity or price raises
    ValueError.
    """,
    holdout_test="""
    assert format_invoice([]) == ['TOTAL = \\u00a30.00']
    assert format_invoice([('tea', 1, 250)]) == ['tea x 1 @ \\u00a32.50 = \\u00a32.50',
                                                 'TOTAL = \\u00a32.50']
    assert format_invoice([('tea', 3, 250)]) == ['tea x 3 @ \\u00a32.50 = \\u00a37.50',
                                                 'TOTAL = \\u00a37.50']
    _mixed = format_invoice([('tea', 1, 5), ('coffee', 2, 100)])
    assert _mixed == ['tea    x 1 @ \\u00a30.05 = \\u00a30.05',
                      'coffee x 2 @ \\u00a31.00 = \\u00a32.00',
                      'TOTAL = \\u00a32.05']
    assert format_invoice([('a', 0, 999)]) == ['a x 0 @ \\u00a39.99 = \\u00a30.00',
                                               'TOTAL = \\u00a30.00']
    assert format_invoice([('a', 2, 0)]) == ['a x 2 @ \\u00a30.00 = \\u00a30.00',
                                             'TOTAL = \\u00a30.00']
    assert format_invoice([('a', 1, 100000)]) == ['a x 1 @ \\u00a31000.00 = \\u00a31000.00',
                                                  'TOTAL = \\u00a31000.00']
    assert format_invoice([('x', 2, 3)])[0].endswith('= \\u00a30.06')
    _bad = 0
    for _items in [[('a', -1, 1)], [('a', 1, -1)]]:
        try:
            format_invoice(_items)
        except ValueError:
            _bad += 1
    assert _bad == 2
    """,
    reference="""
    def format_invoice(items):
        lines = []
        grand = 0
        width = 0
        for description, quantity, price in items:
            if quantity < 0 or price < 0:
                raise ValueError('quantity and price must not be negative')
            if len(description) > width:
                width = len(description)
        for description, quantity, price in items:
            total = quantity * price
            grand += total
            lines.append('%s x %d @ %s = %s' % (
                description.ljust(width), quantity, _money(price), _money(total)))
        lines.append('TOTAL = %s' % _money(grand))
        return lines

    def _money(amount):
        pounds, pence = divmod(amount, 100)
        return '\\u00a3%d.%02d' % (pounds, pence)
    """,
))

SPECS.append(spec(
    id="cal54",
    title="format_duration",
    difficulty="hard",
    objective="""
    def format_duration(seconds: int) -> str

    Describe a length of time in words: years of three hundred and sixty-five
    days, then days, hours, minutes and seconds, leaving out any unit whose
    count is zero.

    Each part is the count, a space and the unit name, pluralised with an s
    unless the count is one. The parts are joined with commas except for the
    last two, which are joined by the word and. A length of zero is the word
    now, and a negative length raises ValueError.
    """,
    holdout_test="""
    assert format_duration(0) == 'now'
    assert format_duration(1) == '1 second'
    assert format_duration(2) == '2 seconds'
    assert format_duration(62) == '1 minute and 2 seconds'
    assert format_duration(120) == '2 minutes'
    assert format_duration(3600) == '1 hour'
    assert format_duration(3662) == '1 hour, 1 minute and 2 seconds'
    assert format_duration(86400) == '1 day'
    assert format_duration(86401) == '1 day and 1 second'
    assert format_duration(31536000) == '1 year'
    assert format_duration(31536001) == '1 year and 1 second'
    assert format_duration(33243586) == '1 year, 19 days, 18 hours, 19 minutes and 46 seconds'
    _err = False
    try:
        format_duration(-1)
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def format_duration(seconds):
        if seconds < 0:
            raise ValueError('seconds must not be negative')
        if seconds == 0:
            return 'now'
        units = [('year', 31536000), ('day', 86400), ('hour', 3600),
                 ('minute', 60), ('second', 1)]
        parts = []
        for name, size in units:
            count = seconds // size
            seconds = seconds % size
            if count:
                parts.append('%d %s%s' % (count, name, '' if count == 1 else 's'))
        if len(parts) == 1:
            return parts[0]
        return ', '.join(parts[:-1]) + ' and ' + parts[-1]
    """,
))

SPECS.append(spec(
    id="cal55",
    title="parse_bytes",
    difficulty="medium",
    objective="""
    def parse_bytes(text: str) -> int

    Read a size such as a number followed by a unit and return the number of
    bytes. The units are B, KB, MB, GB and TB, each a thousand and
    twenty-four times the last, they may be written in any case, and the space
    before them is optional. A bare number is a number of bytes.

    The number may have a fractional part, and the result is the nearest whole
    number of bytes, rounding a half upwards. Surrounding blank space is
    ignored.

    Text with no number, more than one decimal point, an unknown unit, or
    anything else unexpected raises ValueError.
    """,
    holdout_test="""
    assert parse_bytes('10') == 10
    assert parse_bytes(' 10 ') == 10
    assert parse_bytes('1B') == 1
    assert parse_bytes('1 b') == 1
    assert parse_bytes('1KB') == 1024
    assert parse_bytes('1 kb') == 1024
    assert parse_bytes('1.5 KB') == 1536
    assert parse_bytes('0.5 MB') == 524288
    assert parse_bytes('2GB') == 2147483648
    assert parse_bytes('2TB') == 2199023255552
    assert parse_bytes('1.0004 KB') == 1024
    _bad = 0
    for _text in ['', 'abc', 'KB', '1.2.3 KB', '1 XB', '1 K B']:
        try:
            parse_bytes(_text)
        except ValueError:
            _bad += 1
    assert _bad == 6
    """,
    reference="""
    def parse_bytes(text):
        body = text.strip()
        digits = ''
        index = 0
        while index < len(body) and (body[index].isdigit() or body[index] == '.'):
            digits = digits + body[index]
            index += 1
        if not digits or digits == '.' or digits.count('.') > 1:
            raise ValueError('bad number')
        unit = body[index:].strip().upper()
        scales = {'': 1, 'B': 1, 'KB': 1024, 'MB': 1048576,
                  'GB': 1073741824, 'TB': 1099511627776}
        if unit not in scales:
            raise ValueError('unknown unit')
        return int(float(digits) * scales[unit] + 0.5)
    """,
))

SPECS.append(spec(
    id="cal56",
    title="mod97_check",
    difficulty="medium",
    objective="""
    def mod97_check(iban: str) -> bool

    Report whether an international bank account number checks out. Spaces are
    decoration; letters may be written in either case.

    The account number is fifteen to thirty-four characters of letters and
    digits. To verify it, move the first four characters to the end, replace
    each letter by its position in the alphabet plus nine, read the result as
    one long decimal number, and require a remainder of one when divided by
    ninety-seven.

    Anything malformed is simply not valid rather than an error.
    """,
    holdout_test="""
    assert mod97_check('GB82 WEST 1234 5698 7654 32') is True
    assert mod97_check('GB82WEST12345698765432') is True
    assert mod97_check('gb82west12345698765432') is True
    assert mod97_check('GB82 WEST 1234 5698 7654 33') is False
    assert mod97_check('DE89 3704 0044 0532 0130 00') is True
    assert mod97_check('FR14 2004 1010 0505 0001 3M02 606') is True
    assert mod97_check('') is False
    assert mod97_check('GB82') is False
    assert mod97_check('NO9386011117947') is True
    assert mod97_check('RU33AAAAA1234567890BBBBB9876543210') is True
    assert mod97_check('GB611234567890') is False
    assert mod97_check('GB82 WEST 1234 5698 7654 3!') is False
    assert mod97_check('1B82WEST12345698765432') is False
    assert mod97_check('GBX2WEST12345698765432') is False
    """,
    reference="""
    def mod97_check(iban):
        cleaned = iban.replace(' ', '').upper()
        if len(cleaned) < 15 or len(cleaned) > 34:
            return False
        if not cleaned.isalnum():
            return False
        total = 0
        for ch in cleaned[4:] + cleaned[:4]:
            if ch.isdigit():
                total = (total * 10 + int(ch)) % 97
            else:
                total = (total * 100 + (ord(ch) - 55)) % 97
        return total == 1
    """,
))

SPECS.append(spec(
    id="cal57",
    title="merge_k_sorted",
    difficulty="medium",
    objective="""
    def merge_k_sorted(lists: list) -> list

    Merge several already-ascending lists into one ascending list holding
    every value, duplicates included. Where two lists offer an equal value,
    the one from the earlier list comes first.

    No argument may be modified, and a list that is not ascending raises
    ValueError.
    """,
    holdout_test="""
    assert merge_k_sorted([]) == []
    assert merge_k_sorted([[]]) == []
    assert merge_k_sorted([[1, 2, 3]]) == [1, 2, 3]
    assert merge_k_sorted([[1, 4], [2, 3]]) == [1, 2, 3, 4]
    assert merge_k_sorted([[1], [1], [1]]) == [1, 1, 1]
    assert merge_k_sorted([[], [2], []]) == [2]
    assert merge_k_sorted([[1, 5, 9], [2, 6], [3]]) == [1, 2, 3, 5, 6, 9]
    _src = [[3], [1, 2]]
    assert merge_k_sorted(_src) == [1, 2, 3]
    assert _src == [[3], [1, 2]]
    _pairs = merge_k_sorted([[(1, 'a')], [(1, 'b')]])
    assert _pairs == [(1, 'a'), (1, 'b')]
    _err = False
    try:
        merge_k_sorted([[2, 1]])
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def merge_k_sorted(lists):
        for seq in lists:
            for i in range(1, len(seq)):
                if seq[i] < seq[i - 1]:
                    raise ValueError('every list must be ascending')
        cursors = [0] * len(lists)
        out = []
        while True:
            pick = None
            for index in range(len(lists)):
                if cursors[index] >= len(lists[index]):
                    continue
                if pick is None or lists[index][cursors[index]] < lists[pick][cursors[pick]]:
                    pick = index
            if pick is None:
                return out
            out.append(lists[pick][cursors[pick]])
            cursors[pick] += 1
    """,
))

SPECS.append(spec(
    id="cal58",
    title="collapse_runs",
    difficulty="medium",
    objective="""
    def collapse_runs(text: str, threshold: int) -> str

    Shorten long runs of one repeated character. A run of at least `threshold`
    identical characters is replaced by its length, a star and the character
    itself; a shorter run is copied out unchanged.

    A threshold below two raises ValueError, because a run of one could not
    then be written more shortly than itself.
    """,
    holdout_test="""
    assert collapse_runs('', 3) == ''
    assert collapse_runs('abc', 2) == 'abc'
    assert collapse_runs('aab', 2) == '2*ab'
    assert collapse_runs('aab', 3) == 'aab'
    assert collapse_runs('aaab', 3) == '3*ab'
    assert collapse_runs('aaabbc', 3) == '3*abbc'
    assert collapse_runs('aaabbbccc', 3) == '3*a3*b3*c'
    assert collapse_runs('abbba', 3) == 'a3*ba'
    assert collapse_runs('aaaaaaaaaaaa', 3) == '12*a'
    assert collapse_runs('xxyyxx', 2) == '2*x2*y2*x'
    _bad = 0
    for _threshold in [1, 0, -1]:
        try:
            collapse_runs('aaa', _threshold)
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def collapse_runs(text, threshold):
        if threshold < 2:
            raise ValueError('threshold must be at least two')
        out = []
        index = 0
        while index < len(text):
            run = 1
            while index + run < len(text) and text[index + run] == text[index]:
                run += 1
            if run >= threshold:
                out.append('%d*%s' % (run, text[index]))
            else:
                out.append(text[index] * run)
            index += run
        return ''.join(out)
    """,
))

SPECS.append(spec(
    id="cal59",
    title="balance_brackets",
    difficulty="medium",
    objective="""
    def balance_brackets(text: str) -> str

    Insert as few parentheses as possible to make a string of parentheses
    balanced, and return the result.

    A closing parenthesis with nothing to close gets its opening partner
    inserted immediately in front of it, and any opening parenthesis left
    unclosed at the end gets its partner appended, so the answer is determined
    rather than merely correct. Any character other than a parenthesis raises
    ValueError.
    """,
    holdout_test="""
    assert balance_brackets('') == ''
    assert balance_brackets('()') == '()'
    assert balance_brackets('(') == '()'
    assert balance_brackets(')') == '()'
    assert balance_brackets('))') == '()()'
    assert balance_brackets('((') == '(())'
    assert balance_brackets('))(') == '()()()'
    assert balance_brackets('(()') == '(())'
    assert balance_brackets(')(') == '()()'
    assert balance_brackets('()()') == '()()'
    assert balance_brackets('(()))(') == '(())()()'
    _err = False
    try:
        balance_brackets('a')
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def balance_brackets(text):
        out = []
        depth = 0
        for ch in text:
            if ch == '(':
                depth += 1
                out.append(ch)
            elif ch == ')':
                if depth == 0:
                    out.append('(')
                else:
                    depth -= 1
                out.append(ch)
            else:
                raise ValueError('only parentheses are allowed')
        out.append(')' * depth)
        return ''.join(out)
    """,
))

SPECS.append(spec(
    id="cal60",
    title="split_sentences",
    difficulty="hard",
    objective="""
    def split_sentences(text: str) -> list

    Split a paragraph into sentences. A sentence ends at a full stop, a
    question mark or an exclamation mark, and keeps that mark. Surrounding
    blank space is trimmed from each sentence, and text after the last mark is
    a sentence of its own.

    A full stop does not end a sentence when the word immediately before it is
    one of the titles Mr, Mrs, Dr or St. Only a full stop is affected this
    way, and the comparison is exact, so a lowercase spelling is an ordinary
    word.

    Text that holds nothing but blank space gives an empty list.
    """,
    holdout_test="""
    assert split_sentences('') == []
    assert split_sentences('   ') == []
    assert split_sentences('Hi.') == ['Hi.']
    assert split_sentences('Hi. Bye.') == ['Hi.', 'Bye.']
    assert split_sentences('Hi. Bye') == ['Hi.', 'Bye']
    assert split_sentences('Really? Yes! Ok.') == ['Really?', 'Yes!', 'Ok.']
    assert split_sentences('Dr. Who went home. He slept.') == [
        'Dr. Who went home.', 'He slept.']
    assert split_sentences('Mr. and Mrs. Smith left.') == ['Mr. and Mrs. Smith left.']
    assert split_sentences('St. Ives is nice.') == ['St. Ives is nice.']
    assert split_sentences('dr. who') == ['dr.', 'who']
    assert split_sentences('A.B.') == ['A.', 'B.']
    assert split_sentences('Wait...') == ['Wait.', '.', '.']
    """,
    reference="""
    def split_sentences(text):
        titles = ('Mr', 'Mrs', 'Dr', 'St')
        out = []
        current = ''
        for ch in text:
            current = current + ch
            if ch == '.' or ch == '?' or ch == '!':
                word = ''
                j = len(current) - 2
                while j >= 0 and current[j].isalpha():
                    word = current[j] + word
                    j -= 1
                if ch == '.' and word in titles:
                    continue
                if current.strip():
                    out.append(current.strip())
                current = ''
        if current.strip():
            out.append(current.strip())
        return out
    """,
))

SPECS.append(spec(
    id="cal61",
    title="fletcher16",
    difficulty="medium",
    objective="""
    def fletcher16(data: bytes) -> int

    Compute the Fletcher-16 checksum. Two running sums start at zero: the
    first adds each byte in turn, the second adds the first sum after each
    byte, and both are kept modulo two hundred and fifty-five. The checksum is
    the second sum shifted into the high byte with the first sum in the low
    byte.

    Empty input checksums to zero. A value outside the range of a byte raises
    ValueError.
    """,
    holdout_test="""
    assert fletcher16(b'') == 0
    assert fletcher16(b'\\x00') == 0
    assert fletcher16(b'\\x01') == 257
    assert fletcher16(b'abcde') == 51440
    assert fletcher16(b'abcdef') == 8279
    assert fletcher16(b'abcdefgh') == 1575
    assert fletcher16(b'\\xff') == 0
    assert fletcher16(b'\\xff\\xff') == 0
    assert fletcher16(b'\\x01\\x02') == 1027
    assert fletcher16(bytes([1] * 300)) == 3885
    _err = False
    try:
        fletcher16([300])
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def fletcher16(data):
        first = 0
        second = 0
        for byte in data:
            if byte < 0 or byte > 255:
                raise ValueError('bytes must be in range')
            first = (first + byte) % 255
            second = (second + first) % 255
        return (second << 8) | first
    """,
))

SPECS.append(spec(
    id="cal62",
    title="retry_delays",
    difficulty="medium",
    objective="""
    def retry_delays(attempts: int, base: int, cap: int, budget: int) -> list

    Plan the waits between retries. The first wait is `base`, each following
    wait doubles, and no wait exceeds `cap`.

    Waits are planned until either `attempts` of them exist or the next one
    would take the running total past `budget`, in which case planning stops
    without it. A total exactly equal to the budget is allowed.

    A base or cap that is not positive, or a negative number of attempts,
    raises ValueError.
    """,
    holdout_test="""
    assert retry_delays(0, 1, 8, 100) == []
    assert retry_delays(1, 1, 8, 100) == [1]
    assert retry_delays(5, 1, 8, 100) == [1, 2, 4, 8, 8]
    assert retry_delays(5, 1, 8, 10) == [1, 2, 4]
    assert retry_delays(5, 1, 8, 7) == [1, 2, 4]
    assert retry_delays(5, 1, 8, 6) == [1, 2]
    assert retry_delays(3, 2, 3, 100) == [2, 3, 3]
    assert retry_delays(4, 5, 100, 0) == []
    assert retry_delays(4, 1, 1, 100) == [1, 1, 1, 1]
    _bad = 0
    for _call in [lambda: retry_delays(1, 0, 8, 10), lambda: retry_delays(1, 1, 0, 10),
                  lambda: retry_delays(-1, 1, 8, 10)]:
        try:
            _call()
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def retry_delays(attempts, base, cap, budget):
        if base <= 0 or cap <= 0:
            raise ValueError('base and cap must be positive')
        if attempts < 0:
            raise ValueError('attempts must not be negative')
        out = []
        total = 0
        for k in range(attempts):
            delay = min(cap, base * 2 ** k)
            if total + delay > budget:
                break
            out.append(delay)
            total += delay
        return out
    """,
))

SPECS.append(spec(
    id="cal63",
    title="schedule_rr",
    difficulty="medium",
    objective="""
    def schedule_rr(jobs: list, quantum: int) -> list

    Run jobs round robin. Each job is a (name, burst) pair saying how long it
    needs. Starting from the front of the list, each job in turn runs for the
    quantum or for what it has left, whichever is shorter, and if it still has
    work it goes to the back of the queue.

    Return a (name, finishing time) pair for each job in the order the jobs
    finish, where time starts at zero and only running consumes it.

    A quantum that is not positive, or a burst that is not positive, raises
    ValueError.
    """,
    holdout_test="""
    assert schedule_rr([], 2) == []
    assert schedule_rr([('a', 3)], 2) == [('a', 3)]
    assert schedule_rr([('a', 2), ('b', 2)], 2) == [('a', 2), ('b', 4)]
    assert schedule_rr([('a', 3), ('b', 1)], 2) == [('b', 3), ('a', 4)]
    assert schedule_rr([('a', 5), ('b', 5)], 5) == [('a', 5), ('b', 10)]
    assert schedule_rr([('a', 4), ('b', 2)], 1) == [('b', 4), ('a', 6)]
    assert schedule_rr([('a', 1), ('b', 1), ('c', 1)], 3) == [('a', 1), ('b', 2), ('c', 3)]
    assert schedule_rr([('a', 6)], 2) == [('a', 6)]
    _bad = 0
    for _call in [lambda: schedule_rr([('a', 1)], 0), lambda: schedule_rr([('a', 0)], 2),
                  lambda: schedule_rr([('a', -1)], 2)]:
        try:
            _call()
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def schedule_rr(jobs, quantum):
        if quantum <= 0:
            raise ValueError('quantum must be positive')
        queue = []
        for name, burst in jobs:
            if burst <= 0:
                raise ValueError('burst must be positive')
            queue.append([name, burst])
        clock = 0
        out = []
        while queue:
            name, left = queue.pop(0)
            spent = min(quantum, left)
            clock += spent
            left -= spent
            if left:
                queue.append([name, left])
            else:
                out.append((name, clock))
        return out
    """,
))

# The second batch, written after the first was calibrated. Round one measured
# 34 of 63 candidates at the ceiling: the ones that landed in the middle were
# not the most elaborate, they were ordinary algorithms carrying exactly one
# non-obvious rule. These are built to that shape deliberately — the point of
# calibrating first was to learn what "hard enough" actually looks like for
# this model rather than to keep guessing at it.
#
# One candidate (a matrix-padding task) was written and then dropped: it was
# too small to generate the 15 distinct mutants the discrimination gate
# requires. A task whose holdout cannot be shown to fail a wrong answer does
# not go in the file, however convenient the extra data point would be.

SPECS.append(spec(
    id="cal64",
    title="median_fraction",
    difficulty="medium",
    objective="""
    def median_fraction(nums: list) -> tuple

    Return the median of a list of whole numbers as an exact fraction: a
    (numerator, denominator) pair in lowest terms with a positive
    denominator. The list is not necessarily in order and is not modified.

    An even-length list has no middle element, so its median is the average of
    the two middle ones — which is why the answer is a fraction and not a
    number rounded on the way out. An empty list raises ValueError.
    """,
    holdout_test="""
    assert median_fraction([1]) == (1, 1)
    assert median_fraction([1, 2]) == (3, 2)
    assert median_fraction([1, 3]) == (2, 1)
    assert median_fraction([3, 1, 2]) == (2, 1)
    assert median_fraction([1, 2, 3, 4]) == (5, 2)
    assert median_fraction([4, 4]) == (4, 1)
    assert median_fraction([0, 0]) == (0, 1)
    assert median_fraction([-1, -2]) == (-3, 2)
    assert median_fraction([-2, -4]) == (-3, 1)
    assert median_fraction([1, 2, 3, 4, 5, 6]) == (7, 2)
    _src = [5, 1]
    assert median_fraction(_src) == (3, 1)
    assert _src == [5, 1]
    _err = False
    try:
        median_fraction([])
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def median_fraction(nums):
        if not nums:
            raise ValueError('nums must not be empty')
        ordered = sorted(nums)
        size = len(ordered)
        if size % 2:
            total = ordered[size // 2]
            bottom = 1
        else:
            total = ordered[size // 2 - 1] + ordered[size // 2]
            bottom = 2
        a = abs(total)
        b = bottom
        while b:
            a, b = b, a % b
        return (total // a, bottom // a)
    """,
))

SPECS.append(spec(
    id="cal65",
    title="search_descending",
    difficulty="medium",
    objective="""
    def search_descending(seq: list, target: int) -> int

    The sequence is sorted from largest to smallest and may hold repeats.
    Return the position of the first element equal to target, or minus one if
    it is not there.

    The sequence may be long, so the search should halve the range it is
    looking at rather than walk the whole sequence.
    """,
    holdout_test="""
    assert search_descending([], 1) == -1
    assert search_descending([5], 5) == 0
    assert search_descending([5], 4) == -1
    assert search_descending([9, 7, 3], 7) == 1
    assert search_descending([9, 7, 3], 9) == 0
    assert search_descending([9, 7, 3], 3) == 2
    assert search_descending([9, 7, 3], 10) == -1
    assert search_descending([9, 7, 3], 0) == -1
    assert search_descending([9, 7, 7, 7, 3], 7) == 1
    assert search_descending([7, 7, 7], 7) == 0
    assert search_descending([9, 8, 7, 6, 5, 4, 3, 2, 1], 4) == 5
    assert search_descending([2, 2, 1, 1], 1) == 2
    """,
    reference="""
    def search_descending(seq, target):
        lo = 0
        hi = len(seq)
        while lo < hi:
            mid = (lo + hi) // 2
            if seq[mid] > target:
                lo = mid + 1
            else:
                hi = mid
        if lo < len(seq) and seq[lo] == target:
            return lo
        return -1
    """,
))

SPECS.append(spec(
    id="cal66",
    title="rotate_list",
    difficulty="medium",
    objective="""
    def rotate_list(items: list, k: int) -> list

    Return a new list with the items rotated k places to the right, so the
    last item comes round to the front. A negative k rotates to the left, and
    a k larger than the list simply wraps around as many times as it needs to.

    The argument is never modified, and the result is always a fresh list even
    when nothing moves.
    """,
    holdout_test="""
    assert rotate_list([], 3) == []
    assert rotate_list([1, 2, 3], 1) == [3, 1, 2]
    assert rotate_list([1, 2, 3], 0) == [1, 2, 3]
    assert rotate_list([1, 2, 3], 3) == [1, 2, 3]
    assert rotate_list([1, 2, 3], 4) == [3, 1, 2]
    assert rotate_list([1, 2, 3], 7) == [3, 1, 2]
    assert rotate_list([1, 2, 3], -1) == [2, 3, 1]
    assert rotate_list([1, 2, 3], -4) == [2, 3, 1]
    assert rotate_list([1, 2, 3, 4], 2) == [3, 4, 1, 2]
    _src = [1, 2, 3]
    _out = rotate_list(_src, 0)
    _out.append(9)
    assert _src == [1, 2, 3]
    assert rotate_list(_src, 1) == [3, 1, 2]
    assert _src == [1, 2, 3]
    """,
    reference="""
    def rotate_list(items, k):
        size = len(items)
        if size == 0:
            return []
        shift = k % size
        return items[size - shift:] + items[:size - shift]
    """,
))

SPECS.append(spec(
    id="cal67",
    title="headline_case",
    difficulty="medium",
    objective="""
    def headline_case(text: str, small: list = ()) -> str

    Capitalise a title: every word gets an uppercase first letter and
    lowercase elsewhere, and the words are rejoined with single spaces however
    much space separated them before.

    Words listed in `small` stay entirely lowercase, compared without regard
    to case — except that the first and last words of the title are always
    capitalised whatever the list says. An empty title stays empty.
    """,
    holdout_test="""
    assert headline_case('') == ''
    assert headline_case('hello') == 'Hello'
    assert headline_case('HELLO WORLD') == 'Hello World'
    assert headline_case('the quick brown fox', ['the']) == 'The Quick Brown Fox'
    assert headline_case('a tale of two cities', ['of', 'a']) == 'A Tale of Two Cities'
    assert headline_case('the end of', ['of']) == 'The End Of'
    assert headline_case('of mice and men', ['of', 'and']) == 'Of Mice and Men'
    assert headline_case('one', ['one']) == 'One'
    assert headline_case('a  b   c') == 'A B C'
    assert headline_case('THE LORD OF THE RINGS', ['of', 'the']) == 'The Lord of the Rings'
    assert headline_case('x of y', ['OF']) == 'X of Y'
    """,
    reference="""
    def headline_case(text, small=()):
        words = text.split()
        lowered = set()
        for word in small:
            lowered.add(word.lower())
        out = []
        for index, word in enumerate(words):
            body = word.lower()
            if body in lowered and index != 0 and index != len(words) - 1:
                out.append(body)
            else:
                out.append(body[0].upper() + body[1:])
        return ' '.join(out)
    """,
))

SPECS.append(spec(
    id="cal68",
    title="flatten_depth",
    difficulty="medium",
    objective="""
    def flatten_depth(items: list, depth: int) -> list

    Flatten nested lists, but only `depth` levels deep: a depth of zero
    changes nothing, a depth of one unpacks the outermost nesting, and so on.
    Only lists are unpacked — a tuple, a string or anything else is a value
    even when it holds other things.

    The argument is not modified and the result is a new list. A negative
    depth raises ValueError.
    """,
    holdout_test="""
    assert flatten_depth([], 3) == []
    assert flatten_depth([1, 2], 1) == [1, 2]
    assert flatten_depth([1, [2, [3]]], 0) == [1, [2, [3]]]
    assert flatten_depth([1, [2, [3]]], 1) == [1, 2, [3]]
    assert flatten_depth([1, [2, [3]]], 2) == [1, 2, 3]
    assert flatten_depth([1, [2, [3]]], 9) == [1, 2, 3]
    assert flatten_depth([[1], [2]], 1) == [1, 2]
    assert flatten_depth([(1, 2), [3]], 1) == [(1, 2), 3]
    assert flatten_depth(['ab', ['cd']], 1) == ['ab', 'cd']
    assert flatten_depth([[[]]], 2) == []
    _src = [1, [2]]
    assert flatten_depth(_src, 1) == [1, 2]
    assert _src == [1, [2]]
    _err = False
    try:
        flatten_depth([1], -1)
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def flatten_depth(items, depth):
        if depth < 0:
            raise ValueError('depth must not be negative')
        out = []
        for item in items:
            if isinstance(item, list) and depth > 0:
                out.extend(flatten_depth(item, depth - 1))
            else:
                out.append(item)
        return out
    """,
))

SPECS.append(spec(
    id="cal69",
    title="dedupe_keep_last",
    difficulty="medium",
    objective="""
    def dedupe_keep_last(items: list, key=None) -> list

    Remove repeats, keeping the LAST appearance of each value rather than the
    first, and return the survivors in the order those last appearances
    occurred. The argument is not modified.

    Two items are the same when the optional key function says so; without one
    the items are compared directly. The item kept is the original, not its
    key.
    """,
    holdout_test="""
    assert dedupe_keep_last([]) == []
    assert dedupe_keep_last([1, 2, 3]) == [1, 2, 3]
    assert dedupe_keep_last([1, 2, 1]) == [2, 1]
    assert dedupe_keep_last([1, 1, 1]) == [1]
    assert dedupe_keep_last([3, 1, 3, 2, 1]) == [3, 2, 1]
    assert dedupe_keep_last(['a', 'b', 'a', 'b']) == ['a', 'b']
    assert dedupe_keep_last([1, 2, 2, 3, 1]) == [2, 3, 1]
    assert dedupe_keep_last([0, 0, 1]) == [0, 1]
    _src = [1, 2, 1]
    assert dedupe_keep_last(_src) == [2, 1]
    assert _src == [1, 2, 1]
    assert dedupe_keep_last(['aa', 'b', 'cc'], key=len) == ['b', 'cc']
    assert dedupe_keep_last(['A', 'a', 'B'], key=lambda s: s.lower()) == ['a', 'B']
    assert dedupe_keep_last([1, 2, 3, 4], key=lambda n: n % 2) == [3, 4]
    """,
    reference="""
    def dedupe_keep_last(items, key=None):
        seen = set()
        out = []
        for index in range(len(items) - 1, -1, -1):
            item = items[index]
            mark = key(item) if key else item
            if mark in seen:
                continue
            seen.add(mark)
            out.append(item)
        out.reverse()
        return out
    """,
))

SPECS.append(spec(
    id="cal70",
    title="chunk_by_weight",
    difficulty="medium",
    objective="""
    def chunk_by_weight(items: list, limit: int) -> list

    Each item is a (name, weight) pair. Walking the items in order, fill a
    chunk until the next item would take it past the limit, then start a new
    chunk. Return the names, chunk by chunk.

    An item heavier than the limit cannot be packed with anything, so it ends
    up alone in a chunk of its own rather than raising. A limit that is not
    positive raises ValueError.
    """,
    holdout_test="""
    assert chunk_by_weight([], 3) == []
    assert chunk_by_weight([('a', 3)], 3) == [['a']]
    assert chunk_by_weight([('a', 1), ('b', 2)], 3) == [['a', 'b']]
    assert chunk_by_weight([('a', 2), ('b', 2)], 3) == [['a'], ['b']]
    assert chunk_by_weight([('a', 1), ('b', 1), ('c', 1)], 2) == [['a', 'b'], ['c']]
    assert chunk_by_weight([('a', 5)], 3) == [['a']]
    assert chunk_by_weight([('a', 5), ('b', 1)], 3) == [['a'], ['b']]
    assert chunk_by_weight([('a', 1), ('b', 5), ('c', 1)], 3) == [['a'], ['b'], ['c']]
    assert chunk_by_weight([('a', 0), ('b', 0)], 1) == [['a', 'b']]
    _err = False
    try:
        chunk_by_weight([], 0)
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def chunk_by_weight(items, limit):
        if limit <= 0:
            raise ValueError('limit must be positive')
        chunks = []
        current = []
        weight = 0
        for name, size in items:
            if current and weight + size > limit:
                chunks.append(current)
                current = []
                weight = 0
            current.append(name)
            weight += size
        if current:
            chunks.append(current)
        return chunks
    """,
))

SPECS.append(spec(
    id="cal71",
    title="next_greater_cyclic",
    difficulty="medium",
    objective="""
    def next_greater_cyclic(nums: list) -> list

    For each number, report the first number strictly greater than it that
    comes after it, searching to the right and continuing round from the
    beginning of the list when the end is reached. The search never passes the
    number itself again: if nothing in the list is greater, the answer is
    minus one.

    The result has one entry per input, in the same order.
    """,
    holdout_test="""
    assert next_greater_cyclic([]) == []
    assert next_greater_cyclic([1]) == [-1]
    assert next_greater_cyclic([1, 2]) == [2, -1]
    assert next_greater_cyclic([2, 1]) == [-1, 2]
    assert next_greater_cyclic([1, 2, 1]) == [2, -1, 2]
    assert next_greater_cyclic([3, 3]) == [-1, -1]
    assert next_greater_cyclic([1, 2, 3]) == [2, 3, -1]
    assert next_greater_cyclic([5, 4, 3, 2, 1]) == [-1, 5, 5, 5, 5]
    assert next_greater_cyclic([2, 1, 2]) == [-1, 2, -1]
    assert next_greater_cyclic([1, 3, 2, 4]) == [3, 4, 4, -1]
    """,
    reference="""
    def next_greater_cyclic(nums):
        size = len(nums)
        out = []
        for i in range(size):
            answer = -1
            for step in range(1, size):
                value = nums[(i + step) % size]
                if value > nums[i]:
                    answer = value
                    break
            out.append(answer)
        return out
    """,
))

SPECS.append(spec(
    id="cal72",
    title="parse_time_range",
    difficulty="medium",
    objective="""
    def parse_time_range(text: str) -> int

    Read a range of clock times written as two twenty-four-hour stamps joined
    by a hyphen, each exactly two digits, a colon and two digits, and return
    how many minutes it lasts.

    A range whose end is not after its start runs through midnight, so it
    lasts until that time the following day — and a range whose ends are equal
    is therefore a whole day rather than nothing at all.

    A stamp of the wrong shape, an hour above twenty-three, a minute above
    fifty-nine, or a string that is not exactly two stamps raises ValueError.
    """,
    holdout_test="""
    assert parse_time_range('09:00-17:30') == 510
    assert parse_time_range('00:00-00:01') == 1
    assert parse_time_range('23:00-01:00') == 120
    assert parse_time_range('12:00-12:00') == 1440
    assert parse_time_range('00:00-23:59') == 1439
    assert parse_time_range('23:59-00:00') == 1
    assert parse_time_range('00:00-12:00') == 720
    _bad = 0
    for _text in ['9:00-10:00', '09:00', '09:00-24:00', '09:60-10:00',
                  'ab:00-10:00', '09:00-10:00-11:00', '0900-1000', '',
                  '+1:00-10:00', '09:0-10:00', '09:00-1:000']:
        try:
            parse_time_range(_text)
        except ValueError:
            _bad += 1
    assert _bad == 11
    """,
    reference="""
    def parse_time_range(text):
        parts = text.split('-')
        if len(parts) != 2:
            raise ValueError('a range needs exactly one hyphen')
        stamps = []
        for part in parts:
            pieces = part.split(':')
            if len(pieces) != 2 or len(pieces[0]) != 2 or len(pieces[1]) != 2:
                raise ValueError('bad time')
            if not pieces[0].isdigit() or not pieces[1].isdigit():
                raise ValueError('bad time')
            hours = int(pieces[0])
            minutes = int(pieces[1])
            if hours > 23 or minutes > 59:
                raise ValueError('time out of range')
            stamps.append(hours * 60 + minutes)
        span = stamps[1] - stamps[0]
        if span <= 0:
            span += 1440
        return span
    """,
))

SPECS.append(spec(
    id="cal74",
    title="letter_histogram",
    difficulty="medium",
    objective="""
    def letter_histogram(text: str) -> list

    Count how often each letter appears, treating upper and lower case as the
    same letter and ignoring everything that is not a letter. Report the
    counts as (lowercase letter, count) pairs, most frequent first, with
    letters that tie on count in alphabetical order.

    A letter that appears only once is not reported at all.
    """,
    holdout_test="""
    assert letter_histogram('') == []
    assert letter_histogram('abc') == []
    assert letter_histogram('aa') == [('a', 2)]
    assert letter_histogram('aA') == [('a', 2)]
    assert letter_histogram('aabb') == [('a', 2), ('b', 2)]
    assert letter_histogram('bbaa') == [('a', 2), ('b', 2)]
    assert letter_histogram('aaab') == [('a', 3)]
    assert letter_histogram('a a!a b b') == [('a', 3), ('b', 2)]
    assert letter_histogram('112211') == []
    assert letter_histogram('Hello World') == [('l', 3), ('o', 2)]
    """,
    reference="""
    def letter_histogram(text):
        counts = {}
        for ch in text.lower():
            if ch.isalpha():
                counts[ch] = counts.get(ch, 0) + 1
        pairs = []
        for letter in counts:
            if counts[letter] > 1:
                pairs.append((letter, counts[letter]))
        pairs.sort(key=lambda pair: (-pair[1], pair[0]))
        return pairs
    """,
))

SPECS.append(spec(
    id="cal75",
    title="count_subsequences",
    difficulty="hard",
    objective="""
    def count_subsequences(a: str, b: str) -> int

    Count how many ways the first string appears inside the second as a
    subsequence: characters of b chosen in order but not necessarily next to
    one another. Two ways differ if they use different positions of b, even
    where the characters chosen are identical.

    The empty string appears exactly once in anything.
    """,
    holdout_test="""
    assert count_subsequences('', 'abc') == 1
    assert count_subsequences('', '') == 1
    assert count_subsequences('a', '') == 0
    assert count_subsequences('a', 'a') == 1
    assert count_subsequences('a', 'aaa') == 3
    assert count_subsequences('ab', 'abab') == 3
    assert count_subsequences('ba', 'ab') == 0
    assert count_subsequences('abc', 'abc') == 1
    assert count_subsequences('rabbit', 'rabbbit') == 3
    assert count_subsequences('aa', 'aaaa') == 6
    assert count_subsequences('bag', 'babgbag') == 5
    """,
    reference="""
    def count_subsequences(a, b):
        row = [1] + [0] * len(a)
        for ch in b:
            for i in range(len(a), 0, -1):
                if a[i - 1] == ch:
                    row[i] += row[i - 1]
        return row[len(a)]
    """,
))

SPECS.append(spec(
    id="cal76",
    title="compress_path",
    difficulty="hard",
    objective="""
    def compress_path(path: str) -> str

    Tidy a slash-separated path as text, without looking anything up: drop the
    empty pieces left by repeated slashes, drop single dots, and cancel a
    double dot against the piece before it.

    A path that starts at the root cannot climb above it, so a double dot
    there simply disappears. A relative path has nowhere to climb to, so
    leading double dots survive in the result. A relative path that cancels
    away to nothing is the current directory, written as a single dot, and the
    result never ends in a slash.
    """,
    holdout_test="""
    assert compress_path('') == '.'
    assert compress_path('.') == '.'
    assert compress_path('a') == 'a'
    assert compress_path('./a') == 'a'
    assert compress_path('a//b') == 'a/b'
    assert compress_path('a/b/../c') == 'a/c'
    assert compress_path('a/..') == '.'
    assert compress_path('..') == '..'
    assert compress_path('../a') == '../a'
    assert compress_path('../../a') == '../../a'
    assert compress_path('a/../..') == '..'
    assert compress_path('/') == '/'
    assert compress_path('/a/../..') == '/'
    assert compress_path('/a/./b/') == '/a/b'
    assert compress_path('/../a') == '/a'
    """,
    reference="""
    def compress_path(path):
        absolute = path.startswith('/')
        stack = []
        for part in path.split('/'):
            if part == '' or part == '.':
                continue
            if part == '..':
                if stack and stack[-1] != '..':
                    stack.pop()
                elif not absolute:
                    stack.append('..')
                continue
            stack.append(part)
        if absolute:
            return '/' + '/'.join(stack)
        return '/'.join(stack) or '.'
    """,
))

SPECS.append(spec(
    id="cal77",
    title="average_grades",
    difficulty="hard",
    objective="""
    def average_grades(records: list) -> list

    Each record is a (name, scores) pair where scores is a list of whole
    numbers. Return (name, average) pairs with the average rounded to one
    decimal place, highest first, names in alphabetical order among equal
    averages.

    A half rounds AWAY from zero, so an average that lands exactly halfway
    goes to the larger magnitude — which is not what Python's own rounding
    does, and the difference is visible on ordinary marks. A student with no
    scores raises ValueError.
    """,
    holdout_test="""
    assert average_grades([]) == []
    assert average_grades([('a', [1])]) == [('a', 1.0)]
    assert average_grades([('a', [1, 2])]) == [('a', 1.5)]
    assert average_grades([('a', [1, 2, 2])]) == [('a', 1.7)]
    assert average_grades([('a', [9, 0, 0, 0])]) == [('a', 2.3)]
    assert average_grades([('a', [1, 2, 2, 2])]) == [('a', 1.8)]
    assert average_grades([('a', [-9, 0, 0, 0])]) == [('a', -2.3)]
    assert average_grades([('b', [1]), ('a', [1])]) == [('a', 1.0), ('b', 1.0)]
    assert average_grades([('a', [1]), ('b', [2])]) == [('b', 2.0), ('a', 1.0)]
    assert average_grades([('a', [0])]) == [('a', 0.0)]
    assert average_grades([('a', [1, 0, 0])]) == [('a', 0.3)]
    assert average_grades([('a', [2, 0, 0])]) == [('a', 0.7)]
    assert str(average_grades([('a', [0])])[0][1]) == '0.0'
    _err = False
    try:
        average_grades([('a', [])])
    except ValueError:
        _err = True
    assert _err is True
    """,
    reference="""
    def average_grades(records):
        out = []
        for name, scores in records:
            if not scores:
                raise ValueError('a student needs at least one score')
            scaled = sum(scores) * 10
            count = len(scores)
            whole = abs(scaled) // count
            rest = abs(scaled) % count
            if rest * 2 >= count:
                whole += 1
            value = whole / 10 if scaled >= 0 else -whole / 10
            out.append((name, value))
        out.sort(key=lambda pair: (-pair[1], pair[0]))
        return out
    """,
))

SPECS.append(spec(
    id="cal78",
    title="split_evenly",
    difficulty="medium",
    objective="""
    def split_evenly(total: int, parts: int) -> list

    Divide a whole number into the given number of whole parts, as evenly as
    possible, so that the parts add back up to exactly the total and no two
    differ by more than one. The larger parts come first.

    A number of parts that is not positive, or a negative total, raises
    ValueError.
    """,
    holdout_test="""
    assert split_evenly(10, 3) == [4, 3, 3]
    assert split_evenly(9, 3) == [3, 3, 3]
    assert split_evenly(1, 3) == [1, 0, 0]
    assert split_evenly(0, 3) == [0, 0, 0]
    assert split_evenly(5, 1) == [5]
    assert split_evenly(7, 4) == [2, 2, 2, 1]
    assert split_evenly(2, 5) == [1, 1, 0, 0, 0]
    assert sum(split_evenly(97, 7)) == 97
    assert len(split_evenly(97, 7)) == 7
    _bad = 0
    for _call in [lambda: split_evenly(5, 0), lambda: split_evenly(5, -1),
                  lambda: split_evenly(-5, 2)]:
        try:
            _call()
        except ValueError:
            _bad += 1
    assert _bad == 3
    """,
    reference="""
    def split_evenly(total, parts):
        if parts <= 0:
            raise ValueError('parts must be positive')
        if total < 0:
            raise ValueError('total must not be negative')
        base = total // parts
        extra = total % parts
        return [base + 1] * extra + [base] * (parts - extra)
    """,
))

SPECS.append(spec(
    id="cal79",
    title="depth_map",
    difficulty="medium",
    objective="""
    def depth_map(text: str) -> list

    Report the nesting depth of every character of a string of parentheses and
    other characters, as a list of numbers the same length as the string.

    A character outside any parentheses is at depth zero. An opening
    parenthesis carries the depth it opens, and its closing partner carries
    the same depth, so a matching pair reads the same number twice. A
    parenthesis with no partner, in either direction, raises ValueError.
    """,
    holdout_test="""
    assert depth_map('') == []
    assert depth_map('a') == [0]
    assert depth_map('()') == [1, 1]
    assert depth_map('()()') == [1, 1, 1, 1]
    assert depth_map('(())') == [1, 2, 2, 1]
    assert depth_map('(a)') == [1, 1, 1]
    assert depth_map('(a(b))') == [1, 1, 2, 2, 2, 1]
    assert depth_map('a(b)c') == [0, 1, 1, 1, 0]
    assert depth_map('((()))') == [1, 2, 3, 3, 2, 1]
    _bad = 0
    for _text in ['(', ')', ')(', '(()']:
        try:
            depth_map(_text)
        except ValueError:
            _bad += 1
    assert _bad == 4
    """,
    reference="""
    def depth_map(text):
        out = []
        depth = 0
        for ch in text:
            if ch == '(':
                depth += 1
                out.append(depth)
            elif ch == ')':
                if depth == 0:
                    raise ValueError('unbalanced parenthesis')
                out.append(depth)
                depth -= 1
            else:
                out.append(depth)
        if depth:
            raise ValueError('unbalanced parenthesis')
        return out
    """,
))

# @@TASKS@@


# --------------------------------------------------------------------------
# Gates (build_headroom's, plus one more blocked-name source)
# --------------------------------------------------------------------------


def existing_names() -> Dict[str, str]:
    """Entry points already graded elsewhere -> where. Includes headroom_v1.

    `bh.existing_names()` covers bench.py, holdout_v1 and hidden_humaneval.
    headroom_v1 has since been generated against this same model dozens of
    times; reusing one of its names would be measuring recall of a previous
    experiment.
    """
    names = dict(bh.existing_names())
    try:
        data = json.loads(HEADROOM_PATH.read_text(encoding="utf-8"))
    except Exception:
        return names
    for task in data.get("tasks") or []:
        title = task.get("title")
        if isinstance(title, str):
            names.setdefault(title, "headroom_v1.json")
    return names


def static_gates(specs: List[Dict[str, str]]) -> List[str]:
    """Gates 1, 2 and 5 — leakage, prompt hygiene, assertions, name collisions."""
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
            problems.append(f"{tag}: duplicate entry point (also {seen_titles[s['title']]})")
        seen_titles[s["title"]] = tag

        if s["title"] in blocked:
            problems.append(f"{tag}: name already graded in {blocked[s['title']]}")

        if s["title"] not in s["objective"]:
            problems.append(f"{tag}: objective never names the entry point")

        if "assert " in s["objective"]:
            problems.append(f"{tag}: objective contains an assertion")

        for issue in check_task_leakage(public_task(s)):
            problems.append(f"{tag}: leakage — {issue}")

        verdict = prompt_check(s["objective"], s["holdout_test"])
        if not verdict["clean"]:
            problems.append(f"{tag}: prompt_guard — {verdict['detail']}")

        lines = assertion_lines(s["holdout_test"])
        if len(lines) < MIN_ASSERTS:
            problems.append(f"{tag}: {len(lines)} assertions, need >= {MIN_ASSERTS}")
        real = count_real_asserts(s["holdout_test"])
        if real < MIN_ASSERTS:
            problems.append(f"{tag}: {real} observable assertions, need >= {MIN_ASSERTS}")

        objective_flat = " ".join(s["objective"].split())
        novel = [ln for ln in lines if " ".join(ln.split()) not in objective_flat]
        if len(novel) < MIN_ASSERTS:
            problems.append(f"{tag}: holdout only restates the prompt")

        try:
            tree = ast.parse(s["reference"])
        except SyntaxError as e:
            problems.append(f"{tag}: reference does not parse: {e}")
            continue
        if bh._entry_node(tree, s["title"]) is None:
            problems.append(f"{tag}: reference defines no top-level {s['title']}")

        if s["reference"] in s["objective"]:
            problems.append(f"{tag}: reference source appears in the objective")

    return problems


def dynamic_gates(
    specs: List[Dict[str, str]], jobs: int = 6, verbose: bool = True
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Gates 3 and 4 — solvable, and able to tell right from nearly-right.

    Delegated wholesale to `build_headroom.dynamic_gates`: it grades the
    reference against its own holdout and then mutation-scores it. No LLM.
    """
    return bh.dynamic_gates(specs, jobs=jobs, verbose=verbose)


def mutation_scores(specs: List[Dict[str, str]], jobs: int = 6) -> Dict[str, float]:
    _, report = dynamic_gates(specs, jobs=jobs, verbose=False)
    return {row["id"]: float(row["score"]) for row in report}


# --------------------------------------------------------------------------
# Calibration — the only part that talks to a model
# --------------------------------------------------------------------------


@contextmanager
def calibration_env(seed: int) -> Iterator[None]:
    """Pin decoding for one bare generation, then put the environment back.

    Set through the environment because `gems.rose_quartz.router.decode_options`
    reads it at call time. `ETHER_THINKING=0` is not decoration: with thinking
    on, reasoning tokens consumed the whole `num_predict` budget and 59% of an
    earlier 360-sample run returned empty content or timed out, so the run
    measured infrastructure failure and called it code quality.
    """
    updates = {
        "ETHER_SEED": str(seed),
        "ETHER_TEMPERATURE": str(CALIBRATION_TEMPERATURE),
        "ETHER_TOP_P": "0.9",
        "ETHER_TOP_K": "40",
        "ETHER_NUM_CTX": "32768",
        "ETHER_PRESENCE_PENALTY": "0.0",
        "ETHER_FREQUENCY_PENALTY": "0.0",
        "ETHER_REPEAT_PENALTY": "1.0",
        "ETHER_THINKING": "0",
    }
    previous = {k: os.environ.get(k) for k in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def bare_generate(objective: str, seed: int) -> Dict[str, Any]:
    """One user message to the router. No system prompt, no pipeline, no repair.

    This is `scripts/ablation.py`'s `bare` arm, reduced to the part that
    matters here. It is deliberately the weakest possible harness: if a task is
    hard for THIS, the difficulty is in the task and not in the scaffolding.
    """
    from uuid import uuid4

    from core.schemas import ChatMessage, Envelope, RoseQuartzRequest, RoseQuartzResponse
    from gems.rose_quartz.router import RoseQuartz

    router = RoseQuartz(primary_model=os.getenv("ETHER_PRIMARY_MODEL") or None)
    envelope = Envelope(
        task_id=uuid4(),
        target_gem="rose-quartz",
        payload=RoseQuartzRequest(
            messages=[ChatMessage(role="user", content=objective)],
            prefer_local=True,
            max_tokens=CALIBRATION_MAX_TOKENS,
        ),
    )
    started = time.time()
    with calibration_env(seed):
        response = router.execute(envelope)
    elapsed = round(time.time() - started, 2)

    if response.error or not isinstance(response.payload, RoseQuartzResponse):
        return {
            "code": "",
            "model_used": "",
            "error": (response.error.message if response.error else "no router payload")[:300],
            "seconds": elapsed,
        }
    return {
        # `extract_code` is generous to the baseline on purpose: a bare model
        # with no system prompt answers with prose around a fenced block, and
        # scoring that as a syntax error would measure formatting compliance
        # and make every task look harder than it is.
        "code": bh_extract_code(response.payload.content or ""),
        "model_used": response.payload.model_used or "",
        "error": "",
        "seconds": elapsed,
    }


def bh_extract_code(text: str) -> str:
    from scripts.ablation import extract_code

    return extract_code(text)


def _sample_key(task_id: str, seed: int) -> str:
    return f"{task_id}|{seed}"


def load_samples(path: Path) -> Dict[str, Dict[str, Any]]:
    """Completed (task, seed) rows from a previous run. A torn last line is skipped."""
    done: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if "task_id" not in row or "seed" not in row:
            continue
        done[_sample_key(str(row["task_id"]), int(row["seed"]))] = row
    return done


def calibrate(
    specs: Sequence[Dict[str, str]],
    seeds: Sequence[int] = CALIBRATION_SEEDS,
    path: Path = SAMPLES_PATH,
    resume: bool = True,
    verbose: bool = True,
) -> Dict[str, float]:
    """Measured bare pass rate per task. Serial, checkpointed after every sample."""
    from core.holdout import grade_against_holdout

    path.parent.mkdir(parents=True, exist_ok=True)
    done = load_samples(path) if resume else {}
    if not resume and path.exists():
        path.unlink()

    total = len(specs) * len(seeds)
    index = 0
    for s in specs:
        for seed in seeds:
            index += 1
            key = _sample_key(s["id"], seed)
            if key in done:
                continue
            gen = bare_generate(s["objective"], seed)
            passed = False
            reason = gen.get("error") or ""
            if gen["code"]:
                verdict = grade_against_holdout(
                    gen["code"], s["holdout_test"], timeout=CALIBRATION_GRADE_TIMEOUT
                )
                passed = bool(verdict["ok"]) and not verdict.get("leaked")
                reason = str(verdict.get("reason") or "")[:200]
            row = {
                "task_id": s["id"],
                "title": s["title"],
                "seed": seed,
                "passed": passed,
                "reason": reason,
                "model_used": gen.get("model_used", ""),
                "seconds": gen.get("seconds"),
                "chars": len(gen.get("code") or ""),
                "temperature": CALIBRATION_TEMPERATURE,
                "thinking": False,
            }
            # Checkpoint BEFORE anything else can fail. Three hours of GPU is
            # not something to hold in memory.
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            done[key] = row
            if verbose:
                mark = "PASS" if passed else "fail"
                print(
                    f"  [{index:>3}/{total}] {s['id']}/{s['title']:<26} seed={seed} "
                    f"{mark}  {gen.get('seconds')}s  {reason[:60]}",
                    flush=True,
                )

    rates: Dict[str, float] = {}
    for s in specs:
        got = [done[_sample_key(s["id"], seed)] for seed in seeds if _sample_key(s["id"], seed) in done]
        if len(got) == len(seeds):
            rates[s["id"]] = sum(1 for r in got if r["passed"]) / len(seeds)
    return rates


# --------------------------------------------------------------------------
# The measurement
# --------------------------------------------------------------------------
#
# Written by `--emit-measured` after a calibration run and pasted here on
# purpose rather than read from the samples file at import time: the shipped
# dataset must be reproducible from this file alone, and a scratch JSONL is not
# a durable record. Values are pass rates over the three seeds, so they take
# only the values 0, 1/3, 2/3 and 1.

MEASURED_BARE_RATE: Dict[str, float] = {}

MEASURED_BARE_RATE.update({
    'cal01': 3 / 3,
    'cal02': 0 / 3,
    'cal03': 0 / 3,
    'cal04': 0 / 3,
    'cal05': 0 / 3,
    'cal06': 0 / 3,
    'cal07': 2 / 3,
    'cal08': 3 / 3,
    'cal09': 3 / 3,
    'cal10': 3 / 3,
    'cal11': 1 / 3,
    'cal12': 1 / 3,
    'cal13': 2 / 3,
    'cal14': 3 / 3,
    'cal15': 3 / 3,
    'cal16': 0 / 3,
    'cal17': 0 / 3,
    'cal18': 0 / 3,
    'cal19': 0 / 3,
    'cal20': 3 / 3,
    'cal21': 3 / 3,
    'cal22': 3 / 3,
    'cal23': 3 / 3,
    'cal24': 0 / 3,
    'cal25': 3 / 3,
    'cal26': 3 / 3,
    'cal27': 3 / 3,
    'cal28': 2 / 3,
    'cal29': 0 / 3,
    'cal30': 2 / 3,
    'cal31': 2 / 3,
    'cal32': 0 / 3,
    'cal33': 1 / 3,
    'cal34': 0 / 3,
    'cal35': 3 / 3,
    'cal36': 2 / 3,
    'cal37': 3 / 3,
    'cal38': 3 / 3,
    'cal39': 3 / 3,
    'cal40': 0 / 3,
    'cal41': 3 / 3,
    'cal42': 3 / 3,
    'cal43': 1 / 3,
    'cal44': 3 / 3,
    'cal45': 3 / 3,
    'cal46': 3 / 3,
    'cal47': 1 / 3,
    'cal48': 3 / 3,
    'cal49': 2 / 3,
    'cal50': 3 / 3,
    'cal51': 3 / 3,
    'cal52': 2 / 3,
    'cal53': 3 / 3,
    'cal54': 3 / 3,
    'cal55': 3 / 3,
    'cal56': 0 / 3,
    'cal57': 3 / 3,
    'cal58': 3 / 3,
    'cal59': 3 / 3,
    'cal60': 3 / 3,
    'cal61': 2 / 3,
    'cal62': 3 / 3,
    'cal63': 3 / 3,
    'cal64': 3 / 3,
    'cal65': 3 / 3,
    'cal66': 3 / 3,
    'cal67': 3 / 3,
    'cal68': 3 / 3,
    'cal69': 0 / 3,
    'cal70': 3 / 3,
    'cal71': 3 / 3,
    'cal72': 1 / 3,
    'cal74': 3 / 3,
    'cal75': 3 / 3,
    'cal76': 3 / 3,
    'cal77': 3 / 3,
    'cal78': 3 / 3,
    'cal79': 0 / 3,
})


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------


def select_ids(
    specs: Sequence[Dict[str, str]],
    measured: Dict[str, float],
    limit: int = TARGET_SUITE_SIZE,
) -> List[str]:
    """The final suite: deterministic, and explainable in one sentence.

    Every task the bare model solved on all three seeds is out. Every task it
    solved on some but not all is in, always — that band is the entire
    experiment and there is no reason ever to drop one. Floor tasks fill the
    remaining room up to `limit`, hardest-first by id for determinism, and are
    shipped marked `power: none`.

    The earlier version of this function chose bucket counts to hit a target
    mean bare rate of 0.55. That was the wrong objective: a mean is a property
    of the suite, not of its power, and chasing it would have meant *discarding
    informative tasks* to make an average look right.
    """
    middle: List[str] = []
    floor: List[str] = []
    for s in specs:
        rate = measured.get(s["id"])
        # Banded, not thresholded. `rate > MAX_BARE_RATE` on a rounded decimal
        # is how nine 2/3 tasks were dropped as "ceiling" once already.
        if rate is None or band_of(rate) == BAND_CEILING:
            continue
        (floor if band_of(rate) == BAND_FLOOR else middle).append(s["id"])

    chosen = set(middle) | set(sorted(floor)[: max(0, limit - len(middle))])
    order = {s["id"]: i for i, s in enumerate(specs)}
    return sorted(chosen, key=lambda i: order[i])


# --------------------------------------------------------------------------
# Power — simulated, because the analytic version of this was wrong last time
# --------------------------------------------------------------------------


def _phi(x: float) -> float:
    """Standard normal CDF, via erf. No third-party imports anywhere here."""
    import math

    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def wilcoxon_p(diffs: Sequence[float]) -> float:
    """Two-sided Wilcoxon signed-rank p for paired per-task rate differences.

    Zero differences are dropped, |d| are mid-ranked (ties are the norm here:
    every difference is a multiple of 1/3), and the normal approximation with
    the standard tie correction is used. For the 20-40 pairs this suite
    produces that approximation is the conventional choice and is accurate
    enough to plan with; the simulation below applies the same test to the
    same statistic under the null, so any inaccuracy shows up as a false
    positive rate that is reported rather than assumed.
    """
    import math

    nonzero = [d for d in diffs if d != 0.0]
    n = len(nonzero)
    if n == 0:
        return 1.0

    order = sorted(range(n), key=lambda i: abs(nonzero[i]))
    ranks = [0.0] * n
    tie_groups: List[int] = []
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(nonzero[order[j + 1]]) == abs(nonzero[order[i]]):
            j += 1
        average = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = average
        tie_groups.append(j - i + 1)
        i = j + 1

    w_plus = sum(r for r, d in zip(ranks, nonzero) if d > 0)
    mean = n * (n + 1) / 4.0
    correction = sum(t ** 3 - t for t in tie_groups) / 2.0
    variance = (n * (n + 1) * (2 * n + 1) - correction) / 24.0
    if variance <= 0:
        return 1.0
    # Continuity correction. Without it this approximation is anti-conservative
    # on few pairs — four differences of +1/3 scored p=0.0455 where the exact
    # test gives 0.125 — and a power simulation built on it would promise
    # sensitivity the suite does not have. Erring conservative is the only safe
    # direction for a number whose job is to say "this cannot detect that".
    deviation = abs(w_plus - mean)
    z = max(0.0, deviation - 0.5) / math.sqrt(variance)
    return max(0.0, min(1.0, 2.0 * (1.0 - _phi(z))))


def mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar (binomial sign test on the discordant pairs)."""
    from math import comb

    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(0, min(b, c) + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def mcnemar_floor(alpha: float = ALPHA) -> int:
    """Discordant pairs needed before any McNemar result can reach `alpha`.

    Six, at 0.05: with five all-one-sided pairs the smallest attainable p is
    2 * 0.5**5 = 0.0625. `scripts/ablation.py` computes the same number; it is
    restated here so this file's own projections cannot silently disagree.
    """
    k = 1
    while 2.0 * (0.5 ** k) > alpha:
        k += 1
    return k


def _plug_in_p(rate: float) -> float:
    """A believable true pass probability behind a rate measured on 3 seeds.

    The measured rate is not the parameter: 0/3 does not mean "never" and 3/3
    does not mean "always". Using the raw rate would make every floor task
    impossible and every ceiling task certain by assumption — precisely the
    kind of assumption that produced a 0.4-0.7 estimate and a 0.933
    measurement. The Jeffreys posterior mean (k + 1/2) / (n + 1) is the
    conventional small-sample shrinkage and is deliberately conservative here:
    it credits a 0/3 task with a 12.5% chance, so floor tasks are given every
    benefit of the doubt in the power figures below.
    """
    k = round(rate * len(CALIBRATION_SEEDS))
    return (k + 0.5) / (len(CALIBRATION_SEEDS) + 1.0)


def simulate_power(
    rates: Sequence[float],
    delta: float,
    trials: int = POWER_TRIALS,
    seed: int = POWER_SEED,
    alpha: float = ALPHA,
) -> Dict[str, Any]:
    """Monte-Carlo power for the two candidate primary statistics.

    The model: each task has a true bare probability `p`, the scaffold arm has
    `min(1, p + delta)`, both arms are run on the same three seeds per task,
    and both tests are applied to the same simulated run.

      wilcoxon  — signed-rank over the per-task difference in pass RATE. Uses
                  the ordinal information three seeds actually produce.
      mcnemar   — exact, over per-task pass@1 (seed 1 only), which is what the
                  previous ablation reported. Collapsing three seeds to one
                  bit is where most of the information goes.

    Reported together so the difference between them is visible rather than
    asserted.
    """
    import random

    rng = random.Random(seed)
    p_bare = [_plug_in_p(r) for r in rates]
    p_arm = [min(1.0, p + delta) for p in p_bare]
    seeds = len(CALIBRATION_SEEDS)

    wins_w = 0
    wins_m = 0
    pairs_total = 0
    discordant_total = 0
    for _ in range(trials):
        diffs = []
        b = 0
        c = 0
        for pb, pe in zip(p_bare, p_arm):
            bare_draws = [rng.random() < pb for _ in range(seeds)]
            arm_draws = [rng.random() < pe for _ in range(seeds)]
            diffs.append((sum(arm_draws) - sum(bare_draws)) / seeds)
            if arm_draws[0] and not bare_draws[0]:
                b += 1
            elif bare_draws[0] and not arm_draws[0]:
                c += 1
        pairs_total += sum(1 for d in diffs if d != 0)
        discordant_total += b + c
        if wilcoxon_p(diffs) <= alpha:
            wins_w += 1
        if mcnemar_p(b, c) <= alpha:
            wins_m += 1

    return {
        "per_task_lift": round(delta, 4),
        "wilcoxon_power": round(wins_w / trials, 3),
        "mcnemar_power": round(wins_m / trials, 3),
        "mean_nonzero_pairs": round(pairs_total / trials, 1),
        "mean_discordant_pairs": round(discordant_total / trials, 1),
    }


def power_note(measured: Dict[str, float], selected: Sequence[str]) -> Dict[str, Any]:
    """What this suite can and cannot detect, simulated rather than asserted.

    `headroom_v1` shipped with a difficulty estimate and no power calculation
    at all, and the run that followed could not have found an effect if one
    existed. The numbers here are the ones to read before believing any result
    from this file.
    """
    rates = [measured[i] for i in selected if i in measured]
    informative = [r for r in rates if band_of(r) == BAND_INFORMATIVE]

    grid = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    curves = [simulate_power(rates, delta) for delta in grid]
    null = simulate_power(rates, 0.0)

    def mde(key: str) -> Optional[float]:
        for row in curves:
            if row[key] >= POWER_TARGET:
                return row["per_task_lift"]
        return None

    # The same question asked of the informative band alone: if the floor
    # tasks turn out to be impossible for every arm, this is what is left.
    middle_only = [simulate_power(informative, d) for d in (0.10, 0.15)] if informative else []

    return {
        "n_tasks": len(rates),
        "n_informative": len(informative),
        "n_floor": len(rates) - len(informative),
        "measured_bare_mean": round(sum(rates) / len(rates), 4) if rates else 0.0,
        "measured_bare_mean_informative": (
            round(sum(informative) / len(informative), 4) if informative else 0.0
        ),
        "alpha": ALPHA,
        "trials": POWER_TRIALS,
        "primary_test": "wilcoxon signed-rank on per-task pass RATE over 3 seeds",
        "secondary_test": "exact McNemar on per-task pass@1 (seed 1)",
        "mcnemar_min_discordant_pairs": mcnemar_floor(),
        "false_positive_rate_at_zero_effect": {
            "wilcoxon": null["wilcoxon_power"],
            "mcnemar": null["mcnemar_power"],
        },
        "power_curve": curves,
        "power_informative_band_only": middle_only,
        "minimum_detectable_effect_pp": {
            "wilcoxon": None if mde("wilcoxon_power") is None else round(mde("wilcoxon_power") * 100, 1),
            "mcnemar": None if mde("mcnemar_power") is None else round(mde("mcnemar_power") * 100, 1),
        },
    }


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def build_document(
    specs: Sequence[Dict[str, str]] = None,
    measured: Dict[str, float] = None,
) -> Dict[str, Any]:
    specs = list(SPECS if specs is None else specs)
    measured = dict(MEASURED_BARE_RATE if measured is None else measured)
    selected = select_ids(specs, measured)
    chosen = [s for s in specs if s["id"] in set(selected)]
    rejected = [
        {
            "id": s["id"],
            "title": s["title"],
            "difficulty": s["difficulty"],
            "bare_pass_rate": (
                round(measured[s["id"]], 4) if s["id"] in measured else None
            ),
            "band": band_of(measured[s["id"]]) if s["id"] in measured else None,
            "reason": (
                "not calibrated"
                if s["id"] not in measured
                else "bare model solved every seed — at the ceiling, cannot show a lift"
                if measured[s["id"]] > MAX_BARE_RATE
                else "surplus floor task beyond the suite size"
            ),
        }
        for s in specs
        if s["id"] not in set(selected)
    ]

    counts: Dict[str, int] = {}
    for value in measured.values():
        key = f"{value:.3f}"
        counts[key] = counts.get(key, 0) + 1

    return {
        "version": "calibrated-v1",
        "description": (
            "Held-out benchmark whose difficulty was MEASURED, not estimated. Every "
            "candidate was generated three times by the bare model (objective only, "
            "temperature 0.2, seeds 1/2/3, thinking off) and graded against its own "
            "holdout; tasks the bare model solved on all three seeds were discarded "
            "because a task at the ceiling cannot show that a scaffold helped. "
            "Read `distribution` before `tasks`: difficulty on this task class is "
            "bimodal for this model, so most candidates land trivial or impossible "
            "and the informative middle is scarce. Tasks are banded — only "
            "`power: informative` ones generate signal, `power: none` (0/3) ones "
            "ship because cracking one is a real result but they must not be "
            "counted as sample size. Objectives carry a signature and prose only; "
            "assertions live in holdout_test and are never shown to the generator; "
            "reference implementations exist only in scripts/build_calibrated.py, "
            "where they are used for mutation scoring."
        ),
        "gates": {
            "leakage": "core.curriculum.check_task_leakage",
            "prompt": "core.prompt_guard.check",
            "solvable": "core.holdout.grade_against_holdout(reference) == ok",
            "discriminating": f"mutation score >= {MIN_MUTATION_SCORE}",
            "min_assertions": MIN_ASSERTS,
            "min_mutants": MIN_MUTANTS,
            "calibrated": "measured bare pass rate <= 2/3 over 3 seeds",
        },
        "calibration": {
            "arm": "bare — one user message to gems.rose_quartz.router.RoseQuartz",
            "model_env": "ETHER_PRIMARY_MODEL",
            "temperature": CALIBRATION_TEMPERATURE,
            "seeds": list(CALIBRATION_SEEDS),
            "thinking": False,
            "max_tokens": CALIBRATION_MAX_TOKENS,
            "grader": "core.holdout.grade_against_holdout",
            "candidates_calibrated": len(measured),
            "selected": len(chosen),
        },
        "distribution": {
            "note": (
                "Measured bare pass rate over 3 seeds, across every candidate that "
                "passed the offline gates. The shape is the finding: difficulty is "
                "bimodal, not a dial, and the middle band cannot be reached "
                "reliably by writing a harder objective."
            ),
            "by_rate": {key: counts[key] for key in sorted(counts)},
            "by_band": {
                band: sum(1 for v in measured.values() if band_of(v) == band)
                for band in (BAND_FLOOR, BAND_INFORMATIVE, BAND_CEILING)
            },
            "candidates": len(measured),
            "generations": len(measured) * len(CALIBRATION_SEEDS),
        },
        "power": power_note(measured, selected),
        "tasks": [public_task(s, measured.get(s["id"])) for s in chosen],
        "rejected": rejected,
    }


def emit_measured(rates: Dict[str, float]) -> str:
    """The table, as exact fractions of the seed count.

    Written `2 / 3` and not `0.666667`: the decimal is larger than two thirds,
    so a rounded literal compared against a two-thirds threshold silently
    dropped nine informative tasks out of the pool. A rate measured on three
    seeds is a fraction with a known denominator, so it is written as one.
    """
    seeds = len(CALIBRATION_SEEDS)
    lines = ["MEASURED_BARE_RATE.update({"]
    for key in sorted(rates):
        lines.append(f"    {key!r}: {round(rates[key] * seeds)} / {seeds},")
    lines.append("})")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the calibrated benchmark.")
    parser.add_argument("--verify-only", action="store_true", help="run every offline gate, write nothing")
    parser.add_argument("--static-only", action="store_true", help="skip the sandbox gates")
    parser.add_argument("--jobs", type=int, default=6, help="parallel sandbox grades (no LLM)")
    parser.add_argument("--only", default="", help="comma-separated ids/titles")
    parser.add_argument("--calibrate", action="store_true", help="ASK THE MODEL (serial, slow)")
    parser.add_argument("--resume", action="store_true", help="reuse checkpointed samples")
    parser.add_argument("--emit-measured", action="store_true", help="print the MEASURED literal")
    parser.add_argument("--samples", default=str(SAMPLES_PATH))
    parser.add_argument("--json-report", default="")
    args = parser.parse_args(argv)

    specs = list(SPECS)
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        specs = [s for s in specs if s["id"] in wanted or s["title"] in wanted]

    samples_path = Path(args.samples)

    if args.emit_measured:
        done = load_samples(samples_path)
        rates: Dict[str, float] = {}
        for s in specs:
            got = [
                done[_sample_key(s["id"], seed)]
                for seed in CALIBRATION_SEEDS
                if _sample_key(s["id"], seed) in done
            ]
            if len(got) == len(CALIBRATION_SEEDS):
                rates[s["id"]] = sum(1 for r in got if r["passed"]) / len(CALIBRATION_SEEDS)
        print(emit_measured(rates))
        return 0

    print(f"calibrated: {len(specs)} candidates")
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

    if args.calibrate:
        print(
            f"\ncalibrating {len(specs)} candidates x {len(CALIBRATION_SEEDS)} seeds "
            f"= {len(specs) * len(CALIBRATION_SEEDS)} bare generations (serial)"
        )
        rates = calibrate(specs, path=samples_path, resume=args.resume)
        print("\nmeasured bare pass rates:")
        for s in specs:
            if s["id"] in rates:
                print(f"  {s['id']}/{s['title']:<28} {rates[s['id']]:.3f}")
        print("\npaste into MEASURED_BARE_RATE:\n")
        print(emit_measured(rates))
        return 0

    if args.verify_only:
        print("\n--verify-only: all offline gates pass, nothing written")
        return 0

    if not MEASURED_BARE_RATE:
        print(
            "\nREFUSING TO WRITE: no calibration data. Difficulty is measured here, "
            "not asserted — run --calibrate first."
        )
        return 5

    document = build_document(specs, MEASURED_BARE_RATE)
    blob = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    for s in specs:
        for line in s["reference"].splitlines():
            body = line.strip()
            if len(body) > 24 and body in blob:
                print(f"\nREFUSING TO WRITE: reference line from {s['title']} is in the output")
                return 4

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(blob, encoding="utf-8")
    power = document["power"]
    print(
        f"\nwrote {OUT_PATH.relative_to(ROOT)} — {len(document['tasks'])} tasks, "
        f"{len(document['rejected'])} rejected, measured bare rate "
        f"{power['measured_bare_mean']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
