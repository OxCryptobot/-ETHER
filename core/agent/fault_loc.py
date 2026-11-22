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
# Batch 5: caller -> callee edges (repo caller; callee is a repo function or a test-file stub,
# marked "~"). A dispatcher (GemRegistry.execute) is then resolved to the handler the failing
# test actually reached, or to its repo caller when the handler is a test stub.
MAX_EDGES = 1200
_edges: set = set()
_kind_cache: Dict[Any, int] = {}  # 0 = outside the repo, 1 = repo function, 2 = test-file function


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


def _stub_key(code: Any) -> Optional[Tuple[str, str]]:
    """("~tests/x.py", qual) for a function defined in a test file under the root, else None."""
    fn = os.path.realpath(code.co_filename or "")
    if not fn.startswith(_ROOT + os.sep) or not fn.endswith(".py"):
        return None
    rel = fn[len(_ROOT) + 1:].replace(os.sep, "/")
    if "site-packages" in rel or rel.split("/", 1)[0] in (".venv", "venv"):
        return None
    qual = getattr(code, "co_qualname", code.co_name).split(".<locals>", 1)[0]
    return None if qual.startswith("<") else ("~" + rel, qual)


def _kind(code: Any) -> int:
    hit = _kind_cache.get(code)
    if hit is None:
        hit = 1 if _key(code) is not None else (2 if _stub_key(code) is not None else 0)
        _kind_cache[code] = hit
    return hit


def _parent(frame: Any) -> Optional[Tuple[str, str]]:
    f = frame.f_back
    for _ in range(40):
        if f is None:
            return None
        if _kind(f.f_code) == 1:
            return _key(f.f_code)
        f = f.f_back
    return None


def _prof(frame: Any, event: str, arg: Any) -> None:
    if event != "call":
        return
    code = frame.f_code
    kind = _kind(code)
    if kind == 0:
        return
    key = _key(code) if kind == 1 else _stub_key(code)
    if kind == 1 and key not in _seen and len(_cur) < MAX_CALLS:
        _seen.add(key)
        _cur.append(key)
    if len(_edges) < MAX_EDGES:
        parent = _parent(frame)
        if parent is not None and parent != key:
            _edges.add((parent, key))


try:
    import pytest

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(item: Any):  # noqa: D401 - pytest hook
        _cur.clear()
        _seen.clear()
        _edges.clear()
        sys.setprofile(_prof)
        try:
            yield
        finally:
            sys.setprofile(None)
            row = _tests.setdefault(item.nodeid, {})
            row["calls"] = [list(k) for k in _cur]
            row["edges"] = sorted([list(a), list(b)] for a, b in _edges)

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


# ---------------------------------------------------------------- batch 4: hub-aware ranking

HUB_WEIGHT = 0.6
TOKEN_BONUS = 0.2
SINK_FACTOR = 0.25
# logging / reporting sinks run *because* something failed (failure-path-only helpers);
# they are symptoms, not causes. Batch-4 live scan: hub demotion alone moved 22 goals from
# GemRegistry.execute to Pipeline._log, a one-line log_run wrapper.
_SINK_PARTS = frozenset("log logs logger logging warn warning debug print emit telemetry notify".split())
_STOP = frozenset("""assert asserts none true false self test tests error errors expected obtained
result results value values with that this from import return list dict index range
where object module call called should must still into other only""".split())


def tokens(text: str) -> set:
    """Lower-case identifier parts >= 4 chars (snake and camel split), minus stop words."""
    import re

    out = set()
    for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text or ""):
        for part in re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])", word):
            p = part.lower()
            if len(p) >= 4 and p not in _STOP:
                out.add(p)
    return out


def rank(spectra: Dict[str, Any], nodeid: str, hint: str = "") -> List[Tuple[float, int, str, str]]:
    """Ochiai, demoted for hubs and nudged by the failure's own words. Same tuple shape.

    Why (batch 4): Ochiai alone put 24 of 31 SBFL goals on GemRegistry.execute, a
    dispatcher every pipeline test enters. Two cheap signals fix most of that:
    - hub factor 1 - HUB_WEIGHT * ep/nP: a function most *passing* tests also run is
      unlikely to be the one fault (Pearson et al. 2017 find dispatcher-style ties
      are the main loss of SBFL on real faults);
    - sink factor: logging / reporting helpers (log, warn, emit, ...) count a quarter;
    - token bonus: identifiers shared by the function name and the error text / test
      source (e.g. "audit stage vanished" -> _run_audit). Diagnosis only; the prompt
      still holds the error, the test and the current file, never the answer.
    Measured on seeded mutants in docs/results/batch4/sbfl_bench.json."""
    tests = (spectra or {}).get("tests") or {}
    row = tests.get(nodeid) or {}
    calls = [tuple(c) for c in row.get("calls") or []]
    if not calls:
        return []
    failed = [t for t in tests.values() if t.get("outcome") == "failed"]
    passed = [t for t in tests.values() if t.get("outcome") == "passed"]
    nf, np_ = max(1, len(failed)), len(passed)
    fsets = [set(map(tuple, t.get("calls") or [])) for t in failed]
    psets = [set(map(tuple, t.get("calls") or [])) for t in passed]
    words = tokens(hint)
    out = []
    for order, key in enumerate(calls):
        ef = sum(1 for s in fsets if key in s) or 1
        ep = sum(1 for s in psets if key in s)
        score = ef / math.sqrt(nf * (ef + ep))
        if np_:
            score *= 1.0 - HUB_WEIGHT * (ep / np_)
        leaf = key[1].split(".")[-1]
        if _SINK_PARTS & {p.lower() for p in leaf.strip("_").split("_") if p}:
            score *= SINK_FACTOR
        name_tokens = tokens(leaf) | tokens(key[0].rsplit("/", 1)[-1][:-3])
        if words and name_tokens:
            score += TOKEN_BONUS * len(name_tokens & words) / len(name_tokens)
        out.append((round(score, 4), order, key[0], key[1]))
    out.sort(key=lambda r: (-r[0], -r[1]))
    return out


# ---------------------------------------------------------------- batch 5: dispatch + evidence

DISPATCH_FACTOR = 0.2   # a dispatcher only forwards; its own score counts a fifth
DISPATCH_INHERIT = 0.9  # the handler the failing test reached inherits most of it
CALLER_INHERIT = 0.5    # handler is a test stub: the repo caller that built/consumed it gets half
DISPATCH_FANOUT = 10 ** 9  # fan-out-only rule off by default (measured worse: docs/results/batch5)
WHERE_BONUS = 0.35      # pytest "where X = f()" names the function whose value failed
LITERAL_BONUS = 0.3     # a string literal from the error is produced by this function
FRAME_BONUS = 0.25      # a traceback frame points inside this function
_WHERE = None
_LIT = None


def _re():
    global _WHERE, _LIT
    if _WHERE is None:
        import re

        _WHERE = re.compile(r"where .*?=\s*(?:<(?:function|bound method) ([\w.]+)[^>]*>|(?:<[^>]*>\.)?([A-Za-z_][\w.]*))\(")
        _LIT = re.compile(r"""(?:'([^'\n]{6,120})'|"([^"\n]{6,120})")""")
    return _WHERE, _LIT


def dispatchers(spectra: Dict[str, Any]) -> Dict[Tuple[str, str], set]:
    """{caller: callees} for callers that look like dispatchers across the whole run.

    A dispatcher forwards to a handler picked at run time: the registry's `execute`
    calling `<gem>.execute`. Signal: a method with >= 2 distinct callee *methods* of its
    own name (polymorphic dispatch; dunders excluded). DISPATCH_FANOUT (off by default)
    would also count plain fan-out; on the live suite that marked 99 orchestrators."""
    fan: Dict[Tuple[str, str], set] = {}
    for t in ((spectra or {}).get("tests") or {}).values():
        for a, b in t.get("edges") or []:
            fan.setdefault(tuple(a), set()).add(tuple(b))
    out = {}
    for caller, callees in fan.items():
        leaf = caller[1].split(".")[-1]
        if "." not in caller[1] or leaf.startswith("__"):
            same: set = set()  # plain functions / constructors chaining super().__init__ are not dispatch
        else:
            same = {c for c in callees if "." in c[1] and c[1].split(".")[-1] == leaf}
        if len(same) >= 2 or len(callees) >= DISPATCH_FANOUT:
            out[caller] = callees
    return out


def evidence(text: str) -> Dict[str, Any]:
    """Names and literals the failure text points at (never sent to the model; ranking only)."""
    where_re, lit_re = _re()
    names = set()
    for m in where_re.finditer(text or ""):
        names.add((m.group(1) or m.group(2)).split(".")[-1])
    lits = set()
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith(("E ", "AssertionError", "assert ")) or "Error:" in s:
            for m in lit_re.finditer(s):
                lit = (m.group(1) or m.group(2) or "").strip()
                if len(lit) >= 6 and not lit.startswith(("/", "tests/")) and " object at 0x" not in lit:
                    lits.add(lit)
    frames = []
    import re

    for fm in re.finditer(r"^([A-Za-z0-9_./\\-]+\.py):(\d+):", text or "", re.M):
        frames.append((fm.group(1).replace("\\", "/"), int(fm.group(2))))
    for fm in re.finditer(r'File "([^"]+\.py)", line (\d+)', text or ""):
        frames.append((fm.group(1).replace("\\", "/"), int(fm.group(2))))
    return {"names": names, "literals": sorted(lits)[:12], "frames": frames}


_SPANS: Dict[str, Dict[str, Tuple[int, int, str]]] = {}


def _spans(root: str, rel: str) -> Dict[str, Tuple[int, int, str]]:
    """qualname -> (start, end, source) for functions and methods (cached per file)."""
    key = os.path.join(root, rel)
    hit = _SPANS.get(key)
    if hit is not None:
        return hit
    import ast

    out: Dict[str, Tuple[int, int, str]] = {}
    try:
        text = open(key, encoding="utf-8", errors="ignore").read()
        tree = ast.parse(text)
        lines = text.splitlines()

        def walk(body: Any, prefix: str) -> None:
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    q = prefix + node.name
                    out[q] = (node.lineno, node.end_lineno or node.lineno,
                              "\n".join(lines[node.lineno - 1: node.end_lineno]))
                elif isinstance(node, ast.ClassDef):
                    walk(node.body, prefix + node.name + ".")

        walk(tree.body, "")
    except Exception:
        pass
    _SPANS[key] = out
    return out


def _literal_hit(src: str, lit: str) -> bool:
    if lit in src:
        return True
    # f-strings / %-format: the constant head of the message ("risk=" in "risk=0.4")
    head = lit.split("{")[0].split("%")[0]
    for sep in (": ", "=", " ("):
        if sep in head:
            head = head.split(sep)[0] + sep.rstrip()
            break
    return len(head) >= 8 and head in src


def rank5(spectra: Dict[str, Any], nodeid: str, hint: str = "", root: Optional[str] = None,
          text: str = "") -> List[Tuple[float, int, str, str]]:
    """Batch-4 hub rank, then (1) dispatchers resolved to the handler the failing test
    reached (or to the repo caller when that handler is a test stub) and (2) evidence from
    the failure text: pytest `where X = f()` names, string literals the function produces,
    traceback frames inside it. Same tuple shape. Diagnosis only; the prompt is unchanged."""
    base = rank(spectra, nodeid, hint)
    if not base:
        return base
    tests = (spectra or {}).get("tests") or {}
    row = tests.get(nodeid) or {}
    score = {(r[2], r[3]): r[0] for r in base}
    order = {(r[2], r[3]): r[1] for r in base}
    edges = [(tuple(a), tuple(b)) for a, b in row.get("edges") or []]
    disp = dispatchers(spectra) if edges else {}
    for d in [k for k in score if k in disp]:
        raw = score[d]
        score[d] = raw * DISPATCH_FACTOR
        leaf = d[1].split(".")[-1]
        reached = [b for a, b in edges if a == d]
        same = [b for b in reached if b[1].split(".")[-1] == leaf] or reached
        handlers = [b for b in same if not b[0].startswith("~") and b in score]
        if handlers:
            for h in handlers:
                score[h] = max(score[h], raw * DISPATCH_INHERIT)
        else:
            for a, b in edges:
                if b == d and a in score and a not in disp:
                    score[a] = max(score[a], raw * CALLER_INHERIT)
    ev = evidence(text or "")
    if root and (ev["names"] or ev["literals"] or ev["frames"]):
        for key in list(score):
            rel, qual = key
            leaf = qual.split(".")[-1]
            bonus = 0.0
            if leaf in ev["names"]:
                bonus += WHERE_BONUS
            span = _spans(root, rel).get(qual)
            if span is not None:
                if ev["literals"] and any(_literal_hit(span[2], lit) for lit in ev["literals"]):
                    bonus += LITERAL_BONUS
                if any((f == rel or f.endswith("/" + rel)) and span[0] <= ln <= span[1] for f, ln in ev["frames"]):
                    bonus += FRAME_BONUS
            score[key] += bonus
    out = [(round(s, 4), order[k], k[0], k[1]) for k, s in score.items()]
    out.sort(key=lambda r: (-r[0], -r[1]))
    return out
