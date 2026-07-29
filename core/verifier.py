"""A correctness score for generated code WITHOUT a holdout.

Why this exists
---------------
`core/confidence.py` measures "the process exited 0", and `core/holdout.py`
needs assertions the generator never saw. Real tasks have neither: nothing
crashes and there is no hidden test. `docs/FINDINGS.md` §5 measured the
consequence — the repair loop fired only on a non-zero exit, a wrong answer
usually runs fine, and `ether` vs `ether-no-repair` came back bit-identical.

So this module composes a correctness estimate out of independent, cheap
signals that need no oracle:

  parses      hard gate (ast.parse). 0 here means 0 overall.
  not_stub    hard gate. `def solve(n): pass` passes every behavioural signal
              below — it runs, mutates nothing, survives empty input — and
              scored 1.000 under the old metric (FINDINGS §3). An empty body
              is excluded structurally, not deducted from.
  lint        `ruff check` — pyflakes + a few bugbear rules. This is the only
              signal that sees branches the smoke call never executes, which
              is exactly where a small model puts its undefined names.
  executes    module body runs, and a synthesized smoke call returns, inside
              gems.clear_quartz.sandbox.ClearQuartz (imported, never
              reimplemented).
  properties  argument non-mutation / annotated return type / empty input /
              returns-a-value / idempotence, each checked only when it is
              derivable from the signature or the prose.
  consistency (multi-candidate, see `consistency()`) — run every candidate on
              the SAME generated random inputs and reward agreement with the
              majority. Holdout-free, and the reason best-of-N works.

Two rules this module keeps, because `core/confidence.py` broke both:

1. **No signal is counted twice.** `security_clean` and `static_analysis_score`
   there are the same bit with two names, carrying 0.35 of the weight between
   them. Here every signal has one source and one weight.
2. **A signal that cannot be computed scores 0 and says so.** It never defaults
   to a pass. `applicable` records whether the signal could be derived at all,
   so "no property was derivable" is distinguishable from "a property failed",
   and `normalized` gives the score over just the signals that were live.

Nothing in here raises. A broken tool, a missing sandbox, a hostile candidate:
all become a 0 with a diagnostic string, because the caller is a loop that must
keep running and the diagnostics are what it shows the model.
"""

from __future__ import annotations

import ast
import base64
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

PROBE_MARKER = "__ETHER_PROBE__"

# Weights over the three single-candidate signals.
#
# executes (0.45) is the largest because "the code runs and returns something
# for a plausible call" is the single most discriminating fact available
# without an oracle; it is split evenly between the module body executing and
# the smoke call returning, so a module that imports cleanly but cannot be
# called still scores above one that dies on import.
#
# lint (0.25) is weighted well above its usual "style" reputation because the
# rules selected are not style: F821 undefined-name, F823 use-before-assign,
# B006 mutable default, B023 late-binding closure. Every one of them is a bug
# in a branch a smoke call does not reach, and unreached branches are where a
# 3B model fails.
#
# properties (0.30) is a real behavioural check when it is derivable, and 0
# with an explicit diagnostic when it is not.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "executes": 0.45,
    "lint": 0.25,
    "properties": 0.30,
}

DEFAULT_TIMEOUT = 25

# ---------------------------------------------------------------------------
# ruff
# ---------------------------------------------------------------------------

# Rules deliberately chosen for "wrong", not "ugly":
#   E9   syntax / IO errors
#   F    pyflakes: undefined names, unused imports/locals, redefinition,
#        f-strings with no placeholders, `is` against a literal
#   B006 mutable default argument      B008 function call in default
#   B023 loop variable captured late   B026 star-arg unpacking after keyword
#   PLE  pylint errors (bad `return` in generators, etc.)
_RUFF_SELECT = "E9,F,B006,B008,B023,B026,PLE"

# A critical finding zeroes the lint signal outright: an undefined name is not
# a deduction, it is a guarantee that some path is broken.
_LINT_CRITICAL = {"F821", "F822", "F823", "F702", "F706", "F707"}
_LINT_MAJOR = {"F811", "F632", "F502", "F506", "F522", "F524", "B006", "B008", "B023", "B026"}
_LINT_MAJOR_PENALTY = 0.34
_LINT_MINOR_PENALTY = 0.08


def _ruff_bin() -> Optional[str]:
    """Locate ruff: explicit env, then the running venv, then PATH."""
    explicit = os.getenv("ETHER_RUFF_BIN")
    if explicit and Path(explicit).exists():
        return explicit
    venv_bin = Path(sys.executable).parent / ("ruff.exe" if os.name == "nt" else "ruff")
    if venv_bin.exists():
        return str(venv_bin)
    found = shutil.which("ruff")
    return found


def lint(code: str, *, timeout: int = 30) -> Dict[str, Any]:
    """Run ruff over `code`. Returns {score, diagnostics, applicable, findings}.

    `applicable` is False only when ruff itself is unavailable — and the score
    is still 0 in that case, per the module contract. It is never a free pass.
    """
    out: Dict[str, Any] = {
        "score": 0.0,
        "applicable": False,
        "diagnostics": [],
        "findings": [],
    }
    binary = _ruff_bin()
    if not binary:
        out["diagnostics"].append(
            "lint: ruff is not installed or not on PATH — signal scored 0, not skipped"
        )
        return out

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(code or "")
            tmp = fh.name
        proc = subprocess.run(
            [
                binary,
                "check",
                "--isolated",
                "--no-cache",
                "--exit-zero",
                f"--select={_RUFF_SELECT}",
                "--output-format=json",
                tmp,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        raw = (proc.stdout or "").strip()
        if not raw:
            # No findings at all is legitimately clean; ruff prints "[]".
            if proc.returncode != 0 and (proc.stderr or "").strip():
                out["diagnostics"].append(
                    f"lint: ruff failed — {(proc.stderr or '').strip()[:200]} (scored 0)"
                )
                return out
            out["applicable"] = True
            out["score"] = 1.0
            return out
        findings = json.loads(raw)
    except Exception as e:  # ruff crashed, timed out, or emitted non-JSON
        out["diagnostics"].append(f"lint: could not run ruff ({type(e).__name__}: {e}) — scored 0")
        return out
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    out["applicable"] = True
    penalty = 0.0
    critical = False
    for f in findings if isinstance(findings, list) else []:
        code_id = (f.get("code") or "").strip()
        message = (f.get("message") or "").strip()
        row = ((f.get("location") or {}).get("row")) or "?"
        out["findings"].append({"code": code_id or "SyntaxError", "row": row, "message": message})
        fatal = code_id in _LINT_CRITICAL or code_id.startswith(("E9", "PLE"))
        if not code_id or fatal:
            critical = True
            severity = "critical"
        elif code_id in _LINT_MAJOR:
            penalty += _LINT_MAJOR_PENALTY
            severity = "major"
        else:
            penalty += _LINT_MINOR_PENALTY
            severity = "minor"
        out["diagnostics"].append(
            f"lint[{severity}] {code_id or 'SyntaxError'} line {row}: {message}"
        )

    out["score"] = 0.0 if critical else max(0.0, round(1.0 - penalty, 4))
    return out


# ---------------------------------------------------------------------------
# signature analysis / input synthesis
# ---------------------------------------------------------------------------

_SEQ_NAMES = {
    "items", "values", "nums", "numbers", "arr", "array", "lst", "list", "xs",
    "seq", "sequence", "data", "elements", "entries", "records", "rows",
}
_STR_NAMES = {"s", "text", "word", "words", "name", "string", "sentence", "line", "src", "path"}
_INT_NAMES = {
    "n", "num", "count", "k", "i", "j", "size", "length", "limit", "index", "idx", "x", "y",
}
_DICT_NAMES = {"d", "dct", "mapping", "map", "config", "options", "counts", "table"}
_BOOL_NAMES = {"flag", "verbose", "reverse", "strict", "debug", "ascending"}

_TYPE_ARGS: Dict[str, List[str]] = {
    "int": ["5", "3", "0"],
    "float": ["2.5", "1.0"],
    "str": ['"hello world"', '"abc"', '""'],
    "bool": ["True", "False"],
    "list": ["[3, 1, 2]", "[]", "[1]"],
    "tuple": ["(3, 1, 2)", "()"],
    "set": ["{1, 2, 3}", "set()"],
    "dict": ['{"a": 1, "b": 2}', "{}"],
    "bytes": ['b"abc"'],
}

_EMPTY_FOR = {
    "[": "[]",
    "(": "()",
    "{": "{}",
    '"': '""',
    "b": 'b""',
}

_ANNOTATION_TYPES = {
    "int", "float", "str", "bool", "list", "dict", "set", "tuple", "frozenset", "bytes",
}


def _ann_name(node: Optional[ast.expr]) -> str:
    """Best-effort base type name for an annotation (`List[int]` -> `list`)."""
    if node is None:
        return ""
    try:
        if isinstance(node, ast.Subscript):
            return _ann_name(node.value)
        if isinstance(node, ast.Attribute):
            return node.attr.lower()
        if isinstance(node, ast.Name):
            return node.id.lower()
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value.split("[")[0].strip().lower()
        if isinstance(node, ast.BinOp):  # int | None
            return _ann_name(node.left)
    except Exception:
        return ""
    return ""


def _candidates_for_param(name: str, annotation: Optional[ast.expr]) -> List[str]:
    ann = _ann_name(annotation)
    alias = {
        "sequence": "list", "iterable": "list", "mutablesequence": "list",
        "optional": "", "any": "", "union": "",
        "mapping": "dict", "defaultdict": "dict", "counter": "dict",
    }
    ann = alias.get(ann, ann)
    if ann in _TYPE_ARGS:
        return list(_TYPE_ARGS[ann])
    low = (name or "").lower()
    if low in _SEQ_NAMES:
        return list(_TYPE_ARGS["list"])
    if low in _STR_NAMES:
        return list(_TYPE_ARGS["str"])
    if low in _INT_NAMES:
        return list(_TYPE_ARGS["int"])
    if low in _DICT_NAMES:
        return list(_TYPE_ARGS["dict"])
    if low in _BOOL_NAMES:
        return list(_TYPE_ARGS["bool"])
    # Unknown: try the three shapes a stdlib exercise almost always wants.
    return ["[3, 1, 2]", '"hello world"', "5"]


def _module_functions(tree: ast.AST) -> List[ast.FunctionDef]:
    return [
        n
        for n in getattr(tree, "body", [])
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and isinstance(n, ast.FunctionDef)
    ]


def target_function(code: str, objective: str = "") -> Optional[ast.FunctionDef]:
    """Pick the entry point to probe.

    Preference order: a function whose name the objective mentions, then a
    public function that nothing else in the module calls (an entry point, not
    a helper), then the last public function, then the last function.
    """
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return None
    funcs = _module_functions(tree)
    if not funcs:
        return None

    obj = objective or ""
    named = [f for f in funcs if re.search(rf"\b{re.escape(f.name)}\b", obj)]
    if named:
        return named[-1]

    called: set = set()
    for f in funcs:
        for node in ast.walk(f):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
    entry = [f for f in funcs if f.name not in called and not f.name.startswith("_")]
    if entry:
        return entry[-1]
    public = [f for f in funcs if not f.name.startswith("_")]
    return (public or funcs)[-1]


def _required_params(func: ast.FunctionDef) -> List[Tuple[str, Optional[ast.expr]]]:
    args = func.args
    positional = list(args.posonlyargs) + list(args.args)
    if positional and positional[0].arg in ("self", "cls"):
        positional = positional[1:]
    n_defaults = len(args.defaults)
    required = positional[: len(positional) - n_defaults] if n_defaults else positional
    return [(a.arg, a.annotation) for a in required]


def arg_tuples(func: ast.FunctionDef, limit: int = 5) -> List[List[str]]:
    """Candidate argument tuples, as literal SOURCE strings, best guess first.

    The probe tries them in order and keeps the first that does not raise
    TypeError, so a wrong guess about the signature costs a retry rather than
    a false "this code is broken".
    """
    params = _required_params(func)
    if not params:
        return [[]]
    per_param = [_candidates_for_param(n, a) for n, a in params]
    tuples: List[List[str]] = [[c[0] for c in per_param]]
    for i, cands in enumerate(per_param):
        for alt in cands[1:]:
            t = [c[0] for c in per_param]
            t[i] = alt
            if t not in tuples:
                tuples.append(t)
            if len(tuples) >= limit:
                return tuples
    return tuples[:limit]


def _empty_variant(arg_srcs: Sequence[str]) -> Optional[List[str]]:
    """Replace the first sequence-shaped argument with its empty version."""
    out = list(arg_srcs)
    for i, src in enumerate(out):
        s = src.strip()
        if s.startswith("[") and s != "[]":
            out[i] = "[]"
            return out
        if s.startswith("(") and s != "()":
            out[i] = "()"
            return out
        if s.startswith("{") and s not in ("{}", "set()"):
            out[i] = "{}" if ":" in s else "set()"
            return out
        if (s.startswith('"') or s.startswith("'")) and len(s) > 2:
            out[i] = '""'
            return out
        if s.startswith('b"') and len(s) > 3:
            out[i] = 'b""'
            return out
    return None


def is_stub(func: Optional[ast.FunctionDef]) -> bool:
    """True when the target function's body does nothing.

    `def solve(n): pass` scored **1.000** under `core/confidence.py`
    (FINDINGS §3) — it runs, exits 0, mutates nothing, and survives empty
    input, so every behavioural signal reports a pass. A stub is not a
    candidate; it is the absence of one, and it is gated to 0 rather than
    scored, for the same reason a SyntaxError is.
    """
    if func is None:
        return False
    body = list(func.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]  # drop the docstring
    if not body:
        return True
    for node in body:
        if isinstance(node, ast.Pass):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and (
            node.value.value is Ellipsis or node.value.value is None
        ):
            continue
        if isinstance(node, ast.Return) and (
            node.value is None
            or (isinstance(node.value, ast.Constant) and node.value.value is None)
        ):
            continue
        if isinstance(node, ast.Raise):
            exc = node.exc
            name = ""
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                name = exc.func.id
            elif isinstance(exc, ast.Name):
                name = exc.id
            if name == "NotImplementedError":
                continue
        return False
    return True


def _returns_value_expected(objective: str, func: ast.FunctionDef) -> bool:
    """Should a call produce something other than None?

    True unless the annotation says `-> None` or the prose asks for an
    in-place / printing / writing effect.
    """
    if _ann_name(func.returns) == "none" or (
        isinstance(func.returns, ast.Constant) and func.returns.value is None
    ):
        return False
    text = (objective or "").lower() + " " + (ast.get_docstring(func) or "").lower()
    if re.search(r"in[- ]place|in place|prints?\b|printing|writes? to|logs?\b|mutate", text):
        return False
    return True


def _wants_idempotence(objective: str, func: Optional[ast.FunctionDef]) -> bool:
    """Only require idempotence when the prose actually asks for it.

    Most correct functions are not idempotent; asserting it by default would
    manufacture failures. Restricted to explicit prose so the check stays a
    real signal rather than noise.
    """
    text = (objective or "").lower()
    if re.search(r"\bidempotent|idempotence\b", text):
        return True
    if func is not None and re.search(r"\bidempotent\b", (ast.get_docstring(func) or "").lower()):
        return True
    return False


# ---------------------------------------------------------------------------
# sandbox probe
# ---------------------------------------------------------------------------

_PROBE_TEMPLATE = '''
import base64, json, copy

_SPEC = json.loads(base64.b64decode({spec!r}).decode("utf-8"))
_RES = {{"module": {{"ok": False, "err": "probe did not start"}}, "call": None,
        "props": {{}}, "runs": []}}


def _norm(v):
    """Order-stable repr: dict/set iteration order must not decide agreement."""
    try:
        if isinstance(v, dict):
            return "{{" + ", ".join(sorted(_norm(k) + ": " + _norm(x) for k, x in v.items())) + "}}"
        if isinstance(v, (set, frozenset)):
            return "{{" + ", ".join(sorted(_norm(x) for x in v)) + "}}"
        if isinstance(v, float):
            return repr(round(v, 9))
        if isinstance(v, (list, tuple)):
            inner = ", ".join(_norm(x) for x in v)
            return ("[" + inner + "]") if isinstance(v, list) else ("(" + inner + ")")
        return repr(v)
    except Exception:
        return "<unreprable>"


_G = {{"__name__": "__ether_candidate__"}}
try:
    exec(compile(base64.b64decode(_SPEC["src"]).decode("utf-8"), "<candidate>", "exec"), _G)
    _RES["module"] = {{"ok": True, "err": ""}}
except BaseException as _e:
    _RES["module"] = {{"ok": False, "err": type(_e).__name__ + ": " + str(_e)[:300]}}

_FN = None
_name = _SPEC.get("target") or ""
if _name:
    _cand = _G.get(_name)
    if callable(_cand):
        _FN = _cand

_TYPES = {{"int": int, "float": float, "str": str, "bool": bool, "list": list,
          "dict": dict, "set": set, "tuple": tuple, "frozenset": frozenset,
          "bytes": bytes}}


def _mkargs(srcs):
    return [eval(s, {{"__builtins__": __builtins__}}, {{}}) for s in srcs]


def _call(srcs):
    """-> (status, value_or_error, args_before, args_after). status in ok/type/err."""
    try:
        args = _mkargs(srcs)
    except BaseException as e:
        return ("badargs", type(e).__name__ + ": " + str(e)[:200], None, None)
    try:
        before = copy.deepcopy(args)
    except BaseException:
        before = None
    try:
        out = _FN(*args)
    except TypeError as e:
        return ("type", "TypeError: " + str(e)[:200], before, args)
    except BaseException as e:
        return ("err", type(e).__name__ + ": " + str(e)[:200], before, args)
    return ("ok", out, before, args)


if _FN is not None and _SPEC.get("calls"):
    _chosen = None
    for _srcs in _SPEC["calls"]:
        _status, _val, _before, _after = _call(_srcs)
        if _status == "ok":
            _chosen = (_srcs, _val, _before, _after)
            _RES["call"] = {{"ok": True, "args": _srcs, "value": _norm(_val), "err": ""}}
            break
        if _RES["call"] is None or _status == "err":
            _RES["call"] = {{"ok": False, "args": _srcs, "value": None, "err": _val}}
        if _status == "err":
            break

    if _chosen is not None:
        _srcs, _val, _before, _after = _chosen
        _props = _SPEC.get("props") or {{}}
        if _props.get("no_mutation") and _before is not None:
            try:
                same = all(_norm(a) == _norm(b) for a, b in zip(_before, _after))
                _RES["props"]["no_mutation"] = {{
                    "ok": bool(same),
                    "detail": "" if same else "arguments were mutated: "
                              + _norm(_before) + " -> " + _norm(_after),
                }}
            except BaseException as e:
                _RES["props"]["no_mutation"] = {{"ok": False, "detail": str(e)[:150]}}
        rt = _props.get("return_type")
        if rt:
            want = _TYPES.get(rt)
            if want is not None:
                ok = isinstance(_val, want) or (_props.get("optional") and _val is None)
                _RES["props"]["return_type"] = {{
                    "ok": bool(ok),
                    "detail": "" if ok else "annotated -> " + rt + " but returned "
                              + type(_val).__name__,
                }}
        if _props.get("empty"):
            st, v, _b, _a = _call(_props["empty"])
            if st == "ok":
                _RES["props"]["empty_input"] = {{"ok": True, "detail": ""}}
            elif st in ("type",) or (isinstance(v, str) and v.split(":")[0] in ("ValueError",)):
                _RES["props"]["empty_input"] = {{
                    "ok": True, "detail": "rejects empty input deliberately: " + str(v)[:120]}}
            else:
                _RES["props"]["empty_input"] = {{
                    "ok": False, "detail": "crashed on empty input: " + str(v)[:160]}}
        if _props.get("returns_value"):
            _nonnull = _val is not None
            if not _nonnull:
                for _s2 in _SPEC.get("calls") or []:
                    _st2, _v2, _b2, _a2 = _call(_s2)
                    if _st2 == "ok" and _v2 is not None:
                        _nonnull = True
                        break
            _RES["props"]["returns_value"] = {{
                "ok": bool(_nonnull),
                "detail": "" if _nonnull else "returned None for every input tried — "
                          "the function computes nothing",
            }}
        if _props.get("idempotent"):
            try:
                once = _FN(*_mkargs(_srcs))
                twice = _FN(once)
                ok = _norm(once) == _norm(twice)
                _RES["props"]["idempotent"] = {{
                    "ok": bool(ok),
                    "detail": "" if ok else "f(f(x)) != f(x): "
                              + _norm(twice) + " != " + _norm(once),
                }}
            except BaseException as e:
                _RES["props"]["idempotent"] = {{
                    "ok": False,
                    "detail": "f(f(x)) raised " + type(e).__name__ + ": " + str(e)[:120]}}

if _FN is not None and _SPEC.get("runs"):
    for _srcs in _SPEC["runs"]:
        _status, _val, _b, _a = _call(_srcs)
        if _status == "ok":
            _RES["runs"].append({{"ok": True, "value": _norm(_val)}})
        else:
            _RES["runs"].append({{"ok": False, "value": str(_val).split(":")[0]}})
elif _SPEC.get("runs"):
    _RES["runs"] = [{{"ok": False, "value": "NoTarget"}} for _ in _SPEC["runs"]]

print({marker!r} + json.dumps(_RES))
'''


def _build_probe(
    code: str,
    target: str,
    calls: Sequence[Sequence[str]],
    props: Dict[str, Any],
    runs: Sequence[Sequence[str]] = (),
) -> str:
    spec = {
        "src": base64.b64encode((code or "").encode("utf-8")).decode("ascii"),
        "target": target,
        "calls": [list(c) for c in calls],
        "props": props,
        "runs": [list(r) for r in runs],
    }
    blob = base64.b64encode(json.dumps(spec).encode("utf-8")).decode("ascii")
    return _PROBE_TEMPLATE.format(spec=blob, marker=PROBE_MARKER)


def _run_probe(program: str, timeout: int) -> Dict[str, Any]:
    """Execute a probe program in ClearQuartz. Returns {ok, data, error}."""
    out: Dict[str, Any] = {"ok": False, "data": {}, "error": "", "stdout": "", "stderr": ""}
    try:
        from core.pipeline_hooks import no_code_prep
        from core.schemas import Envelope
        from gems.clear_quartz.sandbox import ClearQuartz, RawCodeRequest

        envelope = Envelope(
            task_id=uuid4(),
            target_gem="clear-quartz",
            # The probe IS the program. prepare_code_for_sandbox would rewrite
            # it (assert synthesis, harness, `# file:` splitting) and we would
            # be measuring a different artifact than the one the loop returns.
            payload=RawCodeRequest(code=program, prepare_code=False),
            timeout_seconds=int(timeout),
        )
        with no_code_prep():
            response = ClearQuartz().execute(envelope)
    except Exception as e:
        out["error"] = f"sandbox unavailable: {type(e).__name__}: {e}"
        return out

    if response.error or response.payload is None:
        out["error"] = (
            f"sandbox error: {response.error.message}" if response.error else "no sandbox payload"
        )
        return out

    payload = response.payload
    out["stdout"] = payload.stdout or ""
    out["stderr"] = (payload.stderr or "")[-800:]
    idx = out["stdout"].rfind(PROBE_MARKER)
    if idx < 0:
        out["error"] = (
            "probe produced no result marker "
            f"(exit={payload.exit_code}); stderr: {out['stderr'][-200:]}"
        )
        return out
    try:
        out["data"] = json.loads(out["stdout"][idx + len(PROBE_MARKER):].splitlines()[0])
        out["ok"] = True
    except Exception as e:
        out["error"] = f"probe result was not JSON: {type(e).__name__}: {e}"
    return out


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def parse_check(code: str) -> Tuple[bool, str]:
    """(ok, diagnostic). The hard gate — everything else is meaningless first."""
    if not (code or "").strip():
        return False, "parses: no code (empty candidate)"
    try:
        ast.parse(code)
    except SyntaxError as e:
        line = getattr(e, "lineno", "?")
        return False, f"parses: SyntaxError line {line}: {e.msg}"
    except (ValueError, MemoryError, RecursionError) as e:
        return False, f"parses: {type(e).__name__}: {e}"
    return True, ""


def score(
    code: str,
    objective: str = "",
    *,
    timeout: int = DEFAULT_TIMEOUT,
    weights: Optional[Dict[str, float]] = None,
    run_sandbox: bool = True,
) -> Dict[str, Any]:
    """Score one candidate in [0, 1] with no holdout. Never raises.

    Returns:
      score       weighted over ALL signals; a signal that could not be
                  computed contributes 0, never a default pass.
      normalized  the same score divided by the weight of the signals that
                  were applicable — use this for a task-independent threshold,
                  because a task where nothing is derivable has a lower ceiling.
      coverage    what fraction of the total weight was actually live. A high
                  `normalized` over low `coverage` means "I verified very
                  little, perfectly" — the caller should not treat that as
                  confidence, which is why the loop gates early-stopping on it.
      signals     {name: 0..1}
      applicable  {name: bool} — False means "nothing to check here", which is
                  reported as 0 but is not evidence of a defect.
      diagnostics human-readable strings, safe to paste into a repair prompt.
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items() if k in w})

    result: Dict[str, Any] = {
        "score": 0.0,
        "normalized": 0.0,
        "coverage": 0.0,
        "signals": {
            "parses": 0.0,
            "not_stub": 0.0,
            "lint": 0.0,
            "executes": 0.0,
            "properties": 0.0,
        },
        "applicable": {
            "parses": True,
            "not_stub": True,
            "lint": False,
            "executes": False,
            "properties": False,
        },
        "weights": dict(w),
        "diagnostics": [],
        "target": "",
    }

    try:
        ok, diag = parse_check(code)
        if not ok:
            result["diagnostics"].append(diag)
            return result
        result["signals"]["parses"] = 1.0

        # Second hard gate. Every behavioural signal reports a pass for
        # `def solve(n): pass`, so it has to be excluded structurally.
        func = target_function(code, objective)
        if is_stub(func):
            result["target"] = func.name if func else ""
            result["diagnostics"].append(
                f"not_stub: {func.name if func else 'the target'}() has an empty body "
                "(pass / ... / return None / NotImplementedError) — it implements nothing"
            )
            return result
        result["signals"]["not_stub"] = 1.0

        lint_out = lint(code)
        result["signals"]["lint"] = float(lint_out["score"])
        result["applicable"]["lint"] = bool(lint_out["applicable"])
        result["diagnostics"].extend(lint_out["diagnostics"])

        if run_sandbox:
            exec_out = _execute_and_properties(code, objective, timeout=timeout)
            result["signals"]["executes"] = exec_out["executes"]
            result["signals"]["properties"] = exec_out["properties"]
            result["applicable"]["executes"] = exec_out["executes_applicable"]
            result["applicable"]["properties"] = exec_out["properties_applicable"]
            result["diagnostics"].extend(exec_out["diagnostics"])
            result["target"] = exec_out["target"]
        else:
            result["diagnostics"].append(
                "executes: sandbox execution disabled by caller — signal scored 0"
            )
            result["diagnostics"].append(
                "properties: not checked (execution disabled) — signal scored 0"
            )

        total = sum(w[k] * result["signals"][k] for k in w)
        live = sum(w[k] for k in w if result["applicable"].get(k))
        whole = sum(w.values()) or 1.0
        result["score"] = round(max(0.0, min(1.0, total)), 4)
        result["normalized"] = round(total / live, 4) if live > 0 else 0.0
        result["coverage"] = round(live / whole, 4)
    except Exception as e:  # a verifier that raises takes the loop down with it
        result["diagnostics"].append(f"verifier: internal error {type(e).__name__}: {e}")
    return result


def _execute_and_properties(
    code: str, objective: str, *, timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """One sandbox run yields both the execution and the property signals.

    They share the probe because they share the hard part: constructing a call
    that the candidate actually accepts.
    """
    out: Dict[str, Any] = {
        "executes": 0.0,
        "properties": 0.0,
        "executes_applicable": True,
        "properties_applicable": False,
        "diagnostics": [],
        "target": "",
        "raw": {},
    }
    func = target_function(code, objective)
    target_name = func.name if func else ""
    out["target"] = target_name

    calls: List[List[str]] = []
    props: Dict[str, Any] = {}
    if func is not None:
        calls = arg_tuples(func)
        first = calls[0] if calls else []
        if any(s.strip()[:1] in "[({" for s in first):
            props["no_mutation"] = True
        ret = _ann_name(func.returns)
        if ret in _ANNOTATION_TYPES:
            props["return_type"] = ret
            props["optional"] = bool(
                isinstance(func.returns, ast.Subscript)
                and _ann_name(getattr(func.returns, "value", None)) == "optional"
            )
        empty = _empty_variant(first) if first else None
        if empty:
            props["empty"] = empty
        if _returns_value_expected(objective, func):
            props["returns_value"] = True
        if _wants_idempotence(objective, func):
            props["idempotent"] = True
    else:
        out["diagnostics"].append(
            "executes: no module-level function found to call — call signal scored 0"
        )

    probe = _build_probe(code, target_name, calls, props)
    run = _run_probe(probe, timeout)
    out["raw"] = run
    if not run["ok"]:
        out["diagnostics"].append(f"executes: {run['error']} — signal scored 0")
        out["diagnostics"].append("properties: not checked (probe failed) — signal scored 0")
        return out

    data = run["data"]
    module = data.get("module") or {}
    module_ok = bool(module.get("ok"))
    if not module_ok:
        out["diagnostics"].append(
            f"executes: module body failed to run — {module.get('err', '')}"
        )

    call = data.get("call")
    call_ok = bool(call and call.get("ok"))
    if func is None:
        pass
    elif call is None:
        out["diagnostics"].append(
            "executes: no smoke call could be constructed for "
            f"{target_name}() — signal scored 0"
        )
    elif not call_ok:
        out["diagnostics"].append(
            f"executes: {target_name}({', '.join(call.get('args') or [])}) raised "
            f"{call.get('err', 'an error')}"
        )
    else:
        out["diagnostics"].append(
            f"executes: {target_name}({', '.join(call.get('args') or [])}) -> "
            f"{call.get('value')}"
        )

    out["executes"] = 0.5 * (1.0 if module_ok else 0.0) + 0.5 * (1.0 if call_ok else 0.0)

    checked = data.get("props") or {}
    if checked:
        out["properties_applicable"] = True
        passed = 0
        for name, res in checked.items():
            if res.get("ok"):
                passed += 1
                out["diagnostics"].append(f"property {name}: ok")
            else:
                out["diagnostics"].append(f"property {name}: FAILED — {res.get('detail', '')}")
        out["properties"] = round(passed / len(checked), 4)
    elif props:
        # The properties were derivable; the call they all depend on never
        # succeeded. Reported as unchecked, and deliberately NOT counted as a
        # second failure — the failing call is already priced into `executes`,
        # and charging it twice is the bug core/confidence.py had.
        out["diagnostics"].append(
            f"properties: derivable ({', '.join(sorted(props))}) but not checked — "
            "no smoke call succeeded; signal scored 0"
        )
    else:
        out["diagnostics"].append(
            "properties: no property was derivable from the signature or prose — "
            "signal scored 0 (this is 'unverified', not 'wrong')"
        )
    return out


# ---------------------------------------------------------------------------
# self-consistency across candidates
# ---------------------------------------------------------------------------


def _random_arg(kind_srcs: Sequence[str], rng: random.Random) -> str:
    """A random literal of the same shape as the best-guess candidate."""
    base = (kind_srcs[0] if kind_srcs else "5").strip()
    if base.startswith("["):
        n = rng.randint(0, 6)
        return "[" + ", ".join(str(rng.randint(-9, 9)) for _ in range(n)) + "]"
    if base.startswith("("):
        n = rng.randint(0, 4)
        body = ", ".join(str(rng.randint(-9, 9)) for _ in range(n))
        return "(" + body + (",)" if n == 1 else ")")
    if base.startswith("{") and ":" in base:
        n = rng.randint(0, 3)
        keys = rng.sample(["a", "b", "c", "d", "e"], n) if n else []
        return "{" + ", ".join(f'"{k}": {rng.randint(0, 9)}' for k in keys) + "}"
    if base.startswith("{"):
        n = rng.randint(0, 4)
        return "{" + ", ".join(str(rng.randint(0, 9)) for _ in range(n)) + "}" if n else "set()"
    if base.startswith('"') or base.startswith("'"):
        n = rng.randint(0, 8)
        return '"' + "".join(rng.choice("abcdeABCDE  ") for _ in range(n)) + '"'
    if base in ("True", "False"):
        return rng.choice(["True", "False"])
    if "." in base:
        return str(round(rng.uniform(-10, 10), 3))
    return str(rng.randint(-12, 12))


def generate_inputs(
    code: str, objective: str = "", *, n: int = 6, seed: int = 1234
) -> List[List[str]]:
    """Random argument tuples (as literal source) for the candidate's entry point.

    Derived from ONE candidate's signature and then reused verbatim for every
    candidate, which is the whole point: agreement is only evidence when the
    inputs are identical.
    """
    func = target_function(code, objective)
    if func is None:
        return []
    params = _required_params(func)
    if not params:
        return [[] for _ in range(1)]
    rng = random.Random(seed)
    shapes = [_candidates_for_param(name, ann) for name, ann in params]
    tuples: List[List[str]] = []
    for _ in range(max(1, n)):
        tuples.append([_random_arg(s, rng) for s in shapes])
    return tuples


def consistency(
    candidates: Sequence[str],
    objective: str = "",
    *,
    n_inputs: int = 6,
    seed: int = 1234,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Score each candidate by how often it agrees with the majority.

    The strongest holdout-free signal there is: independent samples from the
    same model rarely make the SAME mistake, so an answer the other draws
    reproduce is more likely right than one that stands alone. Never raises.

    Returns {scores: [0..1 per candidate], applicable, n_inputs, per_input,
    outputs, diagnostics}. `applicable` is False for fewer than two parseable
    candidates — one draw cannot corroborate itself — and every score is then
    0.0, not a default pass.
    """
    n = len(candidates)
    out: Dict[str, Any] = {
        "scores": [0.0] * n,
        "applicable": False,
        "n_inputs": 0,
        "per_input": [],
        "outputs": [[] for _ in range(n)],
        "diagnostics": [],
    }
    try:
        parseable = [i for i, c in enumerate(candidates) if parse_check(c)[0]]
        if len(parseable) < 2:
            out["diagnostics"].append(
                "consistency: fewer than two parseable candidates — "
                "cannot corroborate a single draw, signal scored 0"
            )
            return out

        inputs: List[List[str]] = []
        for i in parseable:
            inputs = generate_inputs(candidates[i], objective, n=n_inputs, seed=seed)
            if inputs:
                break
        if not inputs:
            out["diagnostics"].append(
                "consistency: no callable entry point found — signal scored 0"
            )
            return out
        out["n_inputs"] = len(inputs)

        # Identical inputs for everyone, or agreement means nothing.
        results: Dict[int, List[Dict[str, Any]]] = {}
        for i in parseable:
            func = target_function(candidates[i], objective)
            name = func.name if func else ""
            probe = _build_probe(candidates[i], name, [], {}, runs=inputs)
            run = _run_probe(probe, timeout)
            if not run["ok"]:
                out["diagnostics"].append(
                    f"consistency: candidate {i} probe failed — {run['error']}"
                )
                results[i] = []
                continue
            results[i] = run["data"].get("runs") or []
            out["outputs"][i] = [r.get("value") for r in results[i]]

        live = [i for i in parseable if results.get(i)]
        if len(live) < 2:
            out["diagnostics"].append(
                "consistency: fewer than two candidates produced any output — scored 0"
            )
            return out

        agree = {i: 0.0 for i in live}
        for k in range(len(inputs)):
            tally: Dict[str, List[int]] = {}
            for i in live:
                runs = results[i]
                if k >= len(runs):
                    continue
                entry = runs[k]
                key = ("VAL:" if entry.get("ok") else "EXC:") + str(entry.get("value"))
                tally.setdefault(key, []).append(i)
            if not tally:
                continue
            best_key = max(tally, key=lambda k2: len(tally[k2]))
            majority = tally[best_key]
            out["per_input"].append(
                {"input": inputs[k], "majority": best_key, "size": len(majority)}
            )
            if len(majority) < 2:
                continue  # unanimous disagreement corroborates nothing
            share = (len(majority) - 1) / max(1, len(live) - 1)
            # Agreeing on a raised exception is weaker evidence than agreeing
            # on a value: every candidate that forgot the same guard raises the
            # same way. Half credit, never zero, never full.
            weight = 1.0 if best_key.startswith("VAL:") else 0.5
            for i in majority:
                agree[i] += share * weight

        denom = float(max(1, len(inputs)))
        for i in live:
            out["scores"][i] = round(min(1.0, agree[i] / denom), 4)
        out["applicable"] = True
        out["diagnostics"].append(
            f"consistency: {len(live)} candidates over {len(inputs)} shared random inputs"
        )
    except Exception as e:
        out["diagnostics"].append(f"consistency: internal error {type(e).__name__}: {e}")
    return out
