"""Spectrum-based fault localisation (Ochiai) for failing tests. Batch 3, 2026-11-19.

Why: most failing tests fail on a bare `assert` in the test, so the traceback has
no repo frame and goal_source could not say which function to edit (45 of 76
failures in the batch-3 baseline). Running the test file once with a call
profiler gives, per test, the repo functions it entered. A function that the
failing test runs and the passing tests do not is the likely culprit:

    susp(f) = ef / sqrt(nF * (ef + ep))      (Ochiai; ef/ep = failing/passing tests that called f)

This is diagnosis, not an answer: the prompt still holds only the error, the
test and the current file. The honest gate is unchanged.

The module is a self-contained pytest plugin (no ETHER imports): run_pytest copies
it next to its junit file and loads it with `-p ether_sbfl`, so it also works for
scratch repos. Output: JSON at $ETHER_SBFL_OUT {"root", "tests": {nodeid:
{"outcome", "calls": [[rel, qualname], ...]}}}. Calls keep first-entry order and
are capped per test.
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

MAX_CALLS = 400
_ROOT = os.path.realpath(os.environ.get("ETHER_SBFL_ROOT") or os.getcwd())
_OUT = os.environ.get("ETHER_SBFL_OUT", "")
_cache: Dict[Any, Optional[Tuple[str, str]]] = {}
_tests: Dict[str, Dict[str, Any]] = {}
_cur: List[Tuple[str, str]] = []
_seen: set = set()


def _key(code: Any) -> Optional[Tuple[str, str]]:
    hit = _cache.get(code, False)
    if hit is not False:
        return hit
    fn = os.path.realpath(code.co_filename or "")
    key = None
    if fn.startswith(_ROOT + os.sep) and fn.endswith(".py"):
        rel = fn[len(_ROOT) + 1:].replace(os.sep, "/")
        top = rel.split("/", 1)[0]
        if top not in ("tests", ".venv", "venv") and "site-packages" not in rel and "/test_" not in rel \
                and not rel.split("/")[-1].startswith(("test_", "conftest")):
            qual = getattr(code, "co_qualname", code.co_name)
            qual = qual.split(".<locals>", 1)[0]
            if not qual.startswith("<"):
                key = (rel, qual)
    _cache[code] = key
    return key


def _prof(frame: Any, event: str, arg: Any) -> None:
    if event != "call":
        return
    key = _key(frame.f_code)
    if key is not None and key not in _seen and len(_cur) < MAX_CALLS:
        _seen.add(key)
        _cur.append(key)


try:
    import pytest

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(item: Any):  # noqa: D401 - pytest hook
        _cur.clear()
        _seen.clear()
        sys.setprofile(_prof)
        try:
            yield
        finally:
            sys.setprofile(None)
            _tests.setdefault(item.nodeid, {})["calls"] = [list(k) for k in _cur]

    def pytest_runtest_logreport(report: Any) -> None:
        row = _tests.setdefault(report.nodeid, {})
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            row["outcome"] = report.outcome

    def pytest_sessionfinish(session: Any, exitstatus: Any) -> None:
        if _OUT:
            try:
                with open(_OUT, "w", encoding="utf-8") as fh:
                    json.dump({"root": _ROOT, "tests": _tests}, fh)
            except Exception:
                pass
except Exception:  # pragma: no cover - pytest always present when loaded as a plugin
    pass


def ochiai(spectra: Dict[str, Any], nodeid: str) -> List[Tuple[float, int, str, str]]:
    """Ranked (score, order, rel, qualname) for the functions a failing test called."""
    tests = (spectra or {}).get("tests") or {}
    row = tests.get(nodeid) or {}
    calls = [tuple(c) for c in row.get("calls") or []]
    if not calls:
        return []
    failed = [t for t in tests.values() if t.get("outcome") == "failed"]
    passed = [t for t in tests.values() if t.get("outcome") == "passed"]
    nf = max(1, len(failed))
    fsets = [set(map(tuple, t.get("calls") or [])) for t in failed]
    psets = [set(map(tuple, t.get("calls") or [])) for t in passed]
    out = []
    for order, key in enumerate(calls):
        ef = sum(1 for s in fsets if key in s) or 1
        ep = sum(1 for s in psets if key in s)
        out.append((round(ef / math.sqrt(nf * (ef + ep)), 4), order, key[0], key[1]))
    # higher score first; among ties the function entered last (closest to the failure)
    out.sort(key=lambda r: (-r[0], -r[1]))
    return out
