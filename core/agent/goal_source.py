"""Real goals: one failing test = one goal; lint findings = goals. No answer in the prompt.

Batch 2 (2026-11-19). The honest gate for every goal here is:
  1. the edit is a tool edit to one non-test file (function replace or add),
  2. the target test (or the lint check + affected tests) passes after the edit,
  3. no test that passed before the edit fails after it (regression guard).
The index lives in artifacts/goal_index.json; config/goal_seed.json seeds it so
a fresh host has work before its first scan. A scan shards the test suite so a
tick stays short on the 1650.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

INDEX = "artifacts/goal_index.json"
SEED = "config/goal_seed.json"
INFRA = (
    "FileNotFoundError: docker", "docker daemon", "ConnectionRefusedError", "urlopen error",
    "TimeoutExpired", "ctypes.windll", "winreg", "ModuleNotFoundError: No module named",
)
EASY_KINDS = ("ImportError", "NameError", "AttributeError", "TypeError", "KeyError", "IndentationError")
FRAME = re.compile(r"^([A-Za-z0-9_./\\-]+\.py):(\d+):", re.M)
IMPORT_NAME = re.compile(r"cannot import name '([A-Za-z_][A-Za-z0-9_]*)' from '([\w.]+)'")
MODULE_ATTR = re.compile(r"module '([\w.]+)' has no attribute '([A-Za-z_][A-Za-z0-9_]*)'")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enabled() -> bool:
    return os.getenv("ETHER_GOAL_SOURCE", "1") != "0"


def constants_enabled() -> bool:
    """Batch 3: edits may also replace/add module-level assignments (ETHER_EDIT_CONSTANTS=0 = off)."""
    return os.getenv("ETHER_EDIT_CONSTANTS", "1") != "0"


MAX_ASSIGNS = 4
MAX_ASSIGN_LINES = 40


def _assign_names(node: ast.AST) -> List[str]:
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def _assign_span(tree: ast.Module, name: str) -> Optional[tuple]:
    """(first, last) line of the last top-level `name = ...` (the binding that wins)."""
    span = None
    for node in tree.body:
        if name in _assign_names(node):
            span = (node.lineno, node.end_lineno or node.lineno)
    return span


def _enclosing_assign(path: Path, line: int) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return ""
    for node in tree.body:
        names = _assign_names(node)
        if len(names) == 1 and node.lineno <= line <= (node.end_lineno or node.lineno):
            return names[0]
    return ""


# ---------------------------------------------------------------- pytest runner

def test_env(root: Path, state: Optional[Path] = None) -> Dict[str, str]:
    """Batch 9: credentials and proxies are scrubbed from every gate / scan run (audit W35)."""
    from core.agent.gate_sandbox import scrub_env

    env = scrub_env()
    env["PYTHONPATH"] = str(root)
    env["ETHER_TEST_STATE_ROOT"] = str(state or Path(tempfile.mkdtemp(prefix="ether_state_")))
    env.pop("ETHER_SUPERVISOR", None)
    return env


def mod_rel(root: Path, dotted: str) -> str:
    """Dotted module -> repo path: a/b.py, or a/b/__init__.py for a package (batch 5:
    `from core.loop import loop_runner_enabled` was untargetable because core/loop.py
    does not exist; 2 failing tests were dropped as no_repo_target)."""
    base = dotted.replace(".", "/")
    if not (Path(root) / (base + ".py")).is_file() and (Path(root) / base / "__init__.py").is_file():
        return base + "/__init__.py"
    return base + ".py"


def nodeid_of(root: Path, classname: str, name: str) -> str:
    parts = (classname or "").split(".")
    for cut in range(len(parts), 0, -1):
        rel = "/".join(parts[:cut]) + ".py"
        if (Path(root) / rel).is_file():
            rest = parts[cut:]
            return "::".join([rel, *rest, name])
    return f"{classname}::{name}"


def sbfl_enabled() -> bool:
    """Batch 3: scans profile the test run for fault localisation (ETHER_SBFL=0 = off)."""
    return os.getenv("ETHER_SBFL", "1") != "0"


BYTECODE_WINDOW_S = 300
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "memory", "artifacts", "out"}


def drop_recent_bytecode(root: Path, window_s: int = BYTECODE_WINDOW_S) -> int:
    """Batch 6: delete cached bytecode of .py files written in the last window_s seconds.

    CPython validates a .pyc by the source's mtime (whole seconds) and size. An edit, a revert
    and a second edit of the same length inside one second left the first edit's bytecode
    in __pycache__, so the gate tested the wrong code (seen as a flaky new-module test: a
    correct `return 2 * x` judged with the reverted `return x + 2`). Cheap: one stat per file."""
    now = time.time()
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            try:
                if now - os.stat(path).st_mtime > window_s:
                    continue
            except OSError:
                continue
            cache = os.path.join(dirpath, "__pycache__")
            if not os.path.isdir(cache):
                continue
            stem = f[:-3] + "."
            for c in os.listdir(cache):
                if c.startswith(stem) and c.endswith(".pyc"):
                    try:
                        os.remove(os.path.join(cache, c))
                        n += 1
                    except OSError:
                        pass
    return n


GATE_TIMEOUT_S = int(os.getenv("ETHER_GATE_TIMEOUT_S", "180"))


def run_pytest(root: Path, args: List[str], timeout: Optional[int] = None, sbfl: bool = False,
               sandbox: Optional[bool] = None) -> Dict[str, Any]:
    """Run pytest, return {nodeid: status} plus failure texts. Never writes the repo.

    sbfl=True also records which repo functions each test entered (core/agent/fault_loc.py).
    Batch 9: by default the run happens in a synced sandbox copy (core/agent/gate_sandbox.py)
    with a scrubbed environment; `tamper` lists copy files the run changed; `rc == -9` and
    `timeout: True` mark a run that did not finish (callers must abort, not compare)."""
    from core.agent import gate_sandbox

    real_root = Path(root)
    timeout = GATE_TIMEOUT_S if timeout is None else timeout
    use_box = gate_sandbox.enabled() if sandbox is None else bool(sandbox)
    drop_recent_bytecode(real_root)
    box: Dict[str, Any] = {}
    if use_box:
        try:
            box = gate_sandbox.sync(real_root)
            root = Path(str(box["dir"]))
            drop_recent_bytecode(root)
        except Exception as exc:  # never fall back silently to an unscrubbed in-place run
            return {"ok": False, "rc": -8, "status": {}, "fail": {}, "secs": 0.0, "spectra": {},
                    "sandbox_error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    else:
        root = real_root
    tmp = Path(tempfile.mkdtemp(prefix="ether_pt_"))
    xml = tmp / "r.xml"
    argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short",
            "-o", "junit_family=xunit1", f"--junitxml={xml}", "--continue-on-collection-errors"]
    env = test_env(root, tmp / "state")
    spectra_path = tmp / "sbfl.json"
    if sbfl:
        shutil.copyfile(Path(__file__).with_name("fault_loc.py"), tmp / "ether_sbfl.py")
        env["PYTHONPATH"] = str(root) + os.pathsep + str(tmp)
        env["ETHER_SBFL_OUT"] = str(spectra_path)
        env["ETHER_SBFL_ROOT"] = str(root)
        argv += ["-p", "ether_sbfl"]
    argv += list(args)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=str(root), capture_output=True, text=True, timeout=timeout,
                              env=env)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp, ignore_errors=True)
        return {"ok": False, "rc": -9, "status": {}, "fail": {}, "secs": round(time.monotonic() - t0, 1),
                "timeout": True, "spectra": {}}
    status: Dict[str, str] = {}
    fail: Dict[str, str] = {}
    try:
        tree = ET.parse(xml).getroot()
        for tc in tree.iter("testcase"):
            nid = nodeid_of(root, tc.get("classname") or "", tc.get("name") or "")
            st = "pass"
            for tag in ("failure", "error"):
                el = tc.find(tag)
                if el is not None:
                    st = "fail"
                    fail[nid] = ((el.get("message") or "") + "\n" + (el.text or ""))[-2000:]
            if tc.find("skipped") is not None:
                st = "skip"
            status[nid] = st
    except Exception:
        pass
    spectra: Dict[str, Any] = {}
    if sbfl and spectra_path.is_file():
        try:
            raw = json.loads(spectra_path.read_text(encoding="utf-8"))
            spectra = {"tests": raw.get("tests") or {}}
        except Exception:
            spectra = {}
    shutil.rmtree(tmp, ignore_errors=True)
    row = {"ok": rc == 0, "rc": rc, "status": status, "fail": fail, "secs": round(time.monotonic() - t0, 1),
           "spectra": spectra}
    if use_box:
        row["sandbox"] = True
        try:
            row["tamper"] = gate_sandbox.tamper(real_root, root)
        except Exception as exc:
            row["tamper"] = [f"<tamper check failed: {type(exc).__name__}>"]
    return row


def baseline_abort(res: Dict[str, Any]) -> str:
    """Batch 9 (audit W6): why a baseline run cannot be compared against, or ''."""
    if res.get("timeout") or res.get("rc") == -9:
        return "baseline timeout"
    if res.get("sandbox_error"):
        return "sandbox error: " + str(res["sandbox_error"])[:120]
    if not res.get("status"):
        return "baseline produced no test results"
    return ""


# ---------------------------------------------------------------- failure -> goal

def _enclosing(path: Path, line: int) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return ""
    best = ""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= line <= (node.end_lineno or 0):
            return node.name
        if isinstance(node, ast.ClassDef) and node.lineno <= line <= (node.end_lineno or 0):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.lineno <= line <= (sub.end_lineno or 0):
                    return f"{node.name}.{sub.name}"
            best = node.name
    return best


def _kind(text: str) -> str:
    m = re.search(r"\b([A-Z][A-Za-z]+(?:Error|Exception))\b", text or "")
    return m.group(1) if m else "AssertionError"


def goal_from_failure(root: Path, nodeid: str, text: str,
                      spectra: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """One failing test -> one goal, or None when the failure is infra or untargetable."""
    return classify_failure(root, nodeid, text, spectra)[0]


DROP_REASONS = (
    "collection_error", "infra", "protected_target", "source_text_assert", "no_repo_target", "no_symbol",
    "too_large", "too_many_sites", "test_bug",
)


def _multi_on() -> bool:
    """Batch 5: ETHER_MULTI_EDIT=1 adds multi-target / new-file goals (core/agent/multi_edit.py)."""
    return os.getenv("ETHER_MULTI_EDIT", "0") == "1"

# Batch 4: the 4B replies with the whole function, capped by num_predict. Batch 3 used 240
# tokens for every goal, so 13 of the 50 seed targets could never be written out in full.
# The reply cap now follows the target's size up to REPLY_MAX; bigger targets are dropped
# ("too_large") or, for SBFL, skipped for the next suspect.
REPLY_MIN = 240
CHARS_PER_TOKEN = 3.3


def reply_max() -> int:
    try:
        return max(REPLY_MIN, int(os.getenv("ETHER_REPLY_MAX", "768")))
    except ValueError:
        return 768


def est_tokens(text: str) -> int:
    return int(len(text or "") / CHARS_PER_TOKEN) + 1


def reply_tokens(root: Path, goal: Dict[str, Any]) -> int:
    """num_predict for a real goal: room for the whole current function (+25% and a margin)."""
    if goal.get("span"):
        from core.agent import span_edit

        return max(REPLY_MIN, min(reply_max(), int(est_tokens(span_edit.span_text(root, goal)) * 1.25) + 64))
    if goal.get("kind") == "lint" or goal.get("missing") or goal.get("symbol_kind") == "assign":
        cur = _func_source(Path(root) / goal["file"], goal["symbol"]) if goal.get("symbol_kind") == "assign" else ""
        return max(REPLY_MIN, min(reply_max(), est_tokens(cur) * 2 + 64)) if cur else REPLY_MIN
    cur = _func_source(Path(root) / goal["file"], goal["symbol"])
    return max(REPLY_MIN, min(reply_max(), int(est_tokens(cur) * 1.25) + 64))


def fits_reply(root: Path, goal: Dict[str, Any]) -> bool:
    if goal.get("targets"):
        from core.agent import multi_edit

        return multi_edit.fits(root, goal["targets"])
    if goal.get("missing") or goal.get("kind") == "lint":
        return True
    if goal.get("span"):
        from core.agent import span_edit

        return span_edit.fits(root, goal, reply_max(), est_tokens)
    cur = _func_source(Path(root) / goal["file"], goal["symbol"])
    return not cur or int(est_tokens(cur) * 1.1) <= reply_max()
SOURCE_TEXT = re.compile(r"""(?:Path\(|open\()\s*["'](?:core|scripts|gems|dashboard|\.github)/"""
                         r"""|inspect\.getsource\(|/\s*["'](?:core|scripts|gems|dashboard|\.github)["']\s*/""")
# Batch 6: a NameError raised in the test file itself for a name some repo module defines is a
# test bug (missing import in the test); the host may not edit tests, so it is not a goal.
TEST_NAME_ERROR = re.compile(r"^(tests/[\w/]+\.py):\d+: in \w+\n(?:.*\n){0,3}?E\s+NameError: name '(\w+)' is not defined", re.M)


def _repo_frames(root: Path, text: str) -> List[tuple]:
    """(rel, line) for every frame in a non-test repo file, deepest last."""
    out: List[tuple] = []
    for fm in FRAME.finditer(text or ""):
        rel = fm.group(1).replace("\\", "/")
        base = str(root).replace("\\", "/")
        if rel.startswith(base):
            rel = rel[len(base) + 1:]
        if rel.startswith("/") or ":" in rel[:3] or ".." in rel.split("/"):
            continue
        if (root / rel).is_file() and not rel.startswith("tests/") and "site-packages" not in rel:
            out.append((rel, int(fm.group(2))))
    return out


def classify_failure(root: Path, nodeid: str, text: str, spectra: Optional[Dict[str, Any]] = None) -> tuple:
    """(goal, reason). reason is "goal" or one of DROP_REASONS (batch 3 coverage report).

    Targets, in order: the missing name of an ImportError; the deepest repo frame
    that is not protected (its function, or its module-level assignment when
    ETHER_EDIT_CONSTANTS is on); the function the test imports and calls. The
    prompt is still built from the error, the test and the current file only.
    """
    from core.agent.goal_quality import protected

    root = Path(root)
    if nodeid.startswith("::"):
        return None, "collection_error"  # no test to gate on
    if any(m in (text or "") for m in INFRA):
        repo_module = False
        if _multi_on():  # batch 5: a missing *repo* module is a new-file goal, not infra
            from core.agent import multi_edit

            repo_module = multi_edit.new_module_target(root, text) is not None and \
                not any(m in (text or "") for m in INFRA if not m.startswith("ModuleNotFoundError"))
        if not repo_module:
            return None, "infra"
    test_file = nodeid.split("::", 1)[0]
    saw_protected = False
    for m in (IMPORT_NAME.search(text or ""), MODULE_ATTR.search(text or "")):
        if not m:
            continue
        name, mod = (m.group(1), m.group(2)) if m.re is IMPORT_NAME else (m.group(2), m.group(1))
        rel = mod_rel(root, mod)
        if (root / rel).is_file():
            if protected(rel):
                saw_protected = True
            else:
                return _goal(root, nodeid, test_file, rel, name, True, text, via="import_error"), "goal"
    for rel, line in reversed(_repo_frames(root, text)):
        if protected(rel):
            saw_protected = True
            continue
        symbol = _enclosing(root / rel, line)
        via = "frame"
        if not symbol and constants_enabled():
            symbol = _enclosing_assign(root / rel, line)
            via = "frame_assign"
        if symbol:
            goal = _goal(root, nodeid, test_file, rel, symbol, False, text, via=via)
            if goal is not None and via == "frame" and not fits_reply(root, goal):
                goal = _fit_large(root, goal, nodeid, text, frame_line=line)
            if goal is not None:
                if via == "frame_assign":
                    goal["symbol_kind"] = "assign"
                elif _multi_on():
                    from core.agent import multi_edit

                    alts = multi_edit.frame_alts(root, text, (rel, symbol))
                    if alts:
                        goal["alt_targets"] = alts
                return goal, "goal"
    target, symbol_hint = _target_from_test(root, nodeid)
    if target and symbol_hint:
        goal = _goal(root, nodeid, test_file, target, symbol_hint, False, text, via="test_import")
        if goal is not None and not fits_reply(root, goal):
            # Batch 6: too large to rewrite. A window the failing assert's own literal points at
            # (e.g. the "resolved" list main() writes), else a fitting spectrum suspect, else a
            # window on any evidence.
            from core.agent import span_edit

            strong = span_edit.make_span(root, goal, text, words=span_edit.assert_words(root, nodeid, text),
                                         min_score=2.0, cap_tokens=reply_max())
            if strong is not None and fits_reply(root, strong):
                return strong, "goal"
            suspect = None if _test_imports_only_protected(root, nodeid) else _sbfl_target(root, nodeid, spectra, text)
            if suspect:
                sgoal = _goal(root, nodeid, test_file, suspect[0], suspect[1], False, text, via="sbfl")
                if sgoal is not None:
                    sgoal["suspicion"] = suspect[2]
                    sgoal["large_target"] = f"{target}::{symbol_hint}"
                    return sgoal, "goal"
            goal = _fit_large(root, goal, nodeid, text)
        if goal is not None and _multi_on():
            from core.agent import multi_edit

            alts = multi_edit.test_alts(root, nodeid, (target, symbol_hint))
            if alts:
                goal["alt_targets"] = alts
        return goal, "goal"
    large: list = []
    suspect = None if _test_imports_only_protected(root, nodeid) else _sbfl_target(root, nodeid, spectra, text, large)
    if large and (suspect is None or large[0][2] > SPAN_MARGIN * suspect[2]):
        # Batch 6: the most suspicious function is too large to rewrite -> a window in it,
        # anchored on the failure's evidence (else fall back to the best fitting suspect).
        lgoal = _goal(root, nodeid, test_file, large[0][0], large[0][1], False, text, via="sbfl")
        if lgoal is not None:
            sgoal = _fit_large(root, lgoal, nodeid, text, min_score=2.0)
            if sgoal.get("span"):
                sgoal["suspicion"] = large[0][2]
                return sgoal, "goal"
    if suspect:
        goal = _goal(root, nodeid, test_file, suspect[0], suspect[1], False, text, via="sbfl")
        if goal is not None:
            goal["suspicion"] = suspect[2]
            if _multi_on():
                from core.agent import multi_edit

                alts = multi_edit.sbfl_alts(root, nodeid, spectra, text, (suspect[0], suspect[1]))
                if alts:
                    goal["alt_targets"] = alts
            return goal, "goal"
    multi_reason = ""
    if _multi_on():
        from core.agent import multi_edit

        mgoal, multi_reason = multi_edit.classify(root, nodeid, text)
        if mgoal is not None:
            if multi_edit.fits(root, mgoal["targets"]):
                return mgoal, "goal"
            return None, "too_large"
        if multi_reason == "too_many_sites":
            return None, "too_many_sites"
    if _is_test_bug(root, text):
        return None, "test_bug"
    agoal = _assign_from_test(root, nodeid, text)
    if agoal is not None:
        if not fits_reply(root, agoal):
            agoal = _fit_large(root, agoal, nodeid, text)
        return agoal, "goal"
    if saw_protected or _test_imports_only_protected(root, nodeid):
        return None, "protected_target"
    if not _multi_on():
        from core.agent import multi_edit

        if len(set(multi_edit.SITE.findall(text or ""))) > multi_edit.MAX_TARGETS:
            return None, "too_many_sites"
    if SOURCE_TEXT.search(_test_source(root, nodeid)):
        return None, "source_text_assert"
    if _repo_frames(root, text):
        return None, "no_symbol"
    return None, "no_repo_target"


SBFL_MIN = 0.3  # below this the suspect is mostly noise (shared helpers)


def sbfl_rank() -> str:
    """ETHER_SBFL_RANK: "b5" (default, batch 5) = hub + dispatcher resolution + failure-text
    evidence; "hub" = batch 4 (Ochiai, hub demotion, error-text tokens); "ochiai" = batch 3."""
    mode = os.getenv("ETHER_SBFL_RANK", "b5").strip().lower()
    return mode if mode in ("ochiai", "hub") else "b5"


def _sbfl_target(root: Path, nodeid: str, spectra: Optional[Dict[str, Any]], text: str = "",
                 large: Optional[list] = None) -> Optional[tuple]:
    """Most suspicious editable function the failing test entered, or None.

    Batch 6: when `large` is a list, the best-ranked suspect that is too large to rewrite is
    appended to it as (rel, qual, score, key) so the caller can offer it as a span goal."""
    from core.agent.goal_quality import protected

    if not spectra:
        return None
    try:
        test_src = (Path(root) / nodeid.split("::", 1)[0]).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        test_src = ""
    imported = {mod_rel(root, m) for m in re.findall(r"(?:from|import) ([A-Za-z_][\w.]*)", test_src)}
    best = None
    ranked_calls = sbfl_ranked(root, nodeid, spectra, text)
    for score, order, rel, qual in ranked_calls:
        if score < SBFL_MIN:
            break
        if protected(rel) or Path(rel).name.startswith("_") or not (Path(root) / rel).is_file():
            continue
        if qual.count(".") > 1 or not _is_function(root, rel, qual):
            continue
        key = (score + (0.05 if rel in imported else 0.0), order)
        if not fits_reply(root, {"file": rel, "symbol": qual}):
            if large is not None and (not large or key > large[0][3]):
                large[:] = [(rel, qual, score, key)]
            continue  # cannot be written out in one reply: try the next suspect
        if best is None or key > best[0]:
            best = (key, rel, qual, score)
    return (best[1], best[2], best[3]) if best else None


def sbfl_ranked(root: Path, nodeid: str, spectra: Optional[Dict[str, Any]], text: str = "") -> list:
    """Ranked suspects under the configured ranker (see sbfl_rank)."""
    from core.agent.fault_loc import ochiai, rank, rank5

    mode = sbfl_rank()
    if mode == "ochiai":
        return ochiai(spectra or {}, nodeid)
    hint = (text or "") + "\n" + _test_source(root, nodeid)
    if mode == "hub":
        return rank(spectra or {}, nodeid, hint=hint)
    return rank5(spectra or {}, nodeid, hint=hint, root=str(root), text=text or "")


def _test_imports_only_protected(root: Path, nodeid: str) -> bool:
    from core.agent.goal_quality import protected

    src = _test_source(root, nodeid)
    mods = re.findall(r"(?:from|import) ((?:core|scripts|gems|dashboard)[\w.]*)", src)
    if not mods:
        try:
            module_src = (Path(root) / nodeid.split("::", 1)[0]).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False
        names = set(re.findall(r"\b([A-Za-z_]\w*)\(", src))
        for mm in re.finditer(r"from ((?:core|scripts|gems|dashboard)[\w.]*) import ([\w, ]+)", module_src):
            if any(n.strip() in names for n in mm.group(2).split(",")):
                mods.append(mm.group(1))
    rels = [mod_rel(root, m) for m in mods]
    rels = [r for r in rels if (Path(root) / r).is_file()]
    return bool(rels) and all(protected(r) for r in rels)


def _is_function(root: Path, rel: str, symbol: str) -> bool:
    try:
        tree = ast.parse((Path(root) / rel).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return False
    span_node = None
    body = tree.body
    for name in symbol.split("."):
        span_node = next((n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                          and n.name == name), None)
        if span_node is None:
            return False
        body = getattr(span_node, "body", [])
    return isinstance(span_node, (ast.FunctionDef, ast.AsyncFunctionDef))


def _target_from_test(root: Path, nodeid: str) -> tuple:
    """No repo frame: the first function the test imports and calls, from a non-protected module.

    Handles `from m import f` + `f(`, `import a.b as c` / `from a import b` (module) +
    `c.f(` (batch 3)."""
    from core.agent.goal_quality import protected

    src = _test_source(root, nodeid)
    rel_test = nodeid.split("::", 1)[0]
    try:
        module_src = (Path(root) / rel_test).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "", ""
    for text in (src, module_src):
        for m in re.finditer(r"from ([A-Za-z_][\w.]*) import (?:\(([\w, \n]+)\)|([\w, ]+))", text):
            rel = mod_rel(root, m.group(1))
            listed = (m.group(2) or m.group(3) or "").replace("\n", ",")
            names = [n.strip().split(" as ")[0].strip() for n in listed.split(",") if n.strip()]
            if (Path(root) / rel).is_file() and not protected(rel):
                for name in names:
                    if re.search(rf"\b{re.escape(name)}\(", src) and _is_function(root, rel, name):
                        return rel, name
            for name in names:  # from pkg import module
                sub = m.group(1).replace(".", "/") + "/" + name + ".py"
                if (Path(root) / sub).is_file() and not protected(sub):
                    hit = _called_attr(root, sub, name, src)
                    if hit:
                        return sub, hit
        for m in re.finditer(r"^\s*import ([A-Za-z_][\w.]*)(?: as (\w+))?", text, re.M):
            rel = mod_rel(root, m.group(1))
            alias = m.group(2) or m.group(1)
            if (Path(root) / rel).is_file() and not protected(rel):
                hit = _called_attr(root, rel, alias, src)
                if hit:
                    return rel, hit
    return "", ""


SPAN_MARGIN = 1.1  # a too-large SBFL suspect must outrank the best fitting one by 10% to win a span


def _fit_large(root: Path, goal: Dict[str, Any], nodeid: str, text: str,
               frame_line: Optional[int] = None, min_score: float = 1.0) -> Dict[str, Any]:
    """Batch 6: a too-large function becomes a span goal when evidence anchors a window."""
    from core.agent import span_edit

    sgoal = span_edit.make_span(root, goal, text, _test_source(root, nodeid), frame_line=frame_line,
                                cap_tokens=reply_max(), min_score=min_score)
    return sgoal if sgoal is not None and fits_reply(root, sgoal) else goal


def _is_test_bug(root: Path, text: str) -> bool:
    m = TEST_NAME_ERROR.search(text or "")
    if not m:
        return False
    name = m.group(2)
    pat = re.compile(rf"^(?:{re.escape(name)}\s*[:=]|def {re.escape(name)}\b|class {re.escape(name)}\b)", re.M)
    for d in ("core", "scripts", "gems"):
        for p in (Path(root) / d).rglob("*.py"):
            try:
                if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
                    return True
            except Exception:
                continue
    return False


MAX_ASSIGN_GOAL_LINES = 80


def _assign_from_test(root: Path, nodeid: str, text: str) -> Optional[Dict[str, Any]]:
    """Batch 6: the test imports a module-level CONSTANT and its failing assert reads it -> assign goal.

    Only with ETHER_EDIT_CONSTANTS on, only UPPER_CASE names bound once at module level in a
    non-protected repo file, at most MAX_ASSIGN_GOAL_LINES long, and only when the error text
    or the test's assert lines mention it."""
    from core.agent.goal_quality import protected

    if not constants_enabled():
        return None
    src = _test_source(root, nodeid)
    rel_test = nodeid.split("::", 1)[0]
    try:
        module_src = (Path(root) / rel_test).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    err_idents = set(re.findall(r"\b[A-Za-z_]\w*\b", "\n".join(
        ln for ln in (text or "").splitlines() if ln.lstrip().startswith(("E ", "assert")))))
    # lines of the test that the failing assert reads: the assert itself, or `x = ...` feeding it
    feeds = [ln for ln in src.splitlines() if re.match(r"\s*(\w+)\s*=", ln) and
             re.match(r"\s*(\w+)\s*=", ln).group(1) in err_idents]
    asserts = "\n".join(feeds + [ln for ln in (text or "").splitlines() if ln.lstrip().startswith(("E ", "assert"))])
    for m in re.finditer(r"from ([A-Za-z_][\w.]*) import (?:\(([\w, \n]+)\)|([\w, ]+))", module_src + "\n" + src):
        rel = mod_rel(root, m.group(1))
        if not (Path(root) / rel).is_file() or protected(rel):
            continue
        listed = (m.group(2) or m.group(3) or "").replace("\n", ",")
        for name in [n.strip().split(" as ")[0].strip() for n in listed.split(",") if n.strip()]:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]+", name) or not re.search(rf"\b{name}\b", asserts):
                continue
            try:
                tree = ast.parse((Path(root) / rel).read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            span = _assign_span(tree, name)
            if not span or span[1] - span[0] + 1 > MAX_ASSIGN_GOAL_LINES:
                continue
            goal = _goal(root, nodeid, rel_test, rel, name, False, text, via="test_import_assign")
            if goal is None:
                continue
            goal["symbol_kind"] = "assign"
            return goal
    return None


def _called_attr(root: Path, rel: str, alias: str, src: str) -> str:
    for fm in re.finditer(rf"\b{re.escape(alias)}\.([A-Za-z_]\w*)\(", src):
        if _is_function(root, rel, fm.group(1)):
            return fm.group(1)
    return ""


def _goal(root: Path, nodeid: str, test_file: str, target: str, symbol: str, missing: bool, text: str,
          via: str) -> Optional[Dict[str, Any]]:
    from core.agent.goal_quality import protected

    if protected(target):
        return None
    gid = "fix_" + re.sub(r"[^A-Za-z0-9_]+", "_", nodeid.split("::", 1)[-1])[:60]
    return {
        "via": via,
        "id": gid,
        "kind": "fix_test",
        "nodeid": nodeid,
        "test_file": test_file,
        "file": target,
        "symbol": symbol,
        "missing": bool(missing),
        "test_import": via == "test_import",
        "error_kind": _kind(text),
        "error": (text or "").strip()[-700:],
    }


def tractability(root: Path, goal: Dict[str, Any]) -> float:
    """Higher = more likely a 4B with file-local context fixes it in one edit."""
    score = 0.5
    if goal.get("error_kind") in EASY_KINDS:
        score += 0.25
    if goal.get("missing"):
        score += 0.1
    if goal.get("via") == "test_import":
        score -= 0.15  # the failing line is in the test; the culprit may be elsewhere
    if goal.get("via") == "sbfl":
        score -= 0.2  # localised by spectrum, not by a frame: least certain target
    try:
        lines = len((Path(root) / goal["file"]).read_text(encoding="utf-8", errors="ignore").splitlines())
    except Exception:
        lines = 2000
    score -= min(0.3, lines / 2000.0)
    if goal.get("kind") == "lint":
        score += 0.15
    if len(str(goal.get("error") or "")) > 600:
        score -= 0.05
    if "." in str(goal.get("symbol") or ""):
        score -= 0.05
    return round(max(0.0, min(1.0, score)), 3)


# ---------------------------------------------------------------- lint -> goal

LINT_RULES = ("F821", "F811", "F841")


def ruff_bin() -> Optional[str]:
    """ruff on PATH, else next to the interpreter (the host's .venv\\Scripts is not on
    pythonw's PATH, so lint goals were silently empty there)."""
    found = shutil.which("ruff")
    if found:
        return found
    for name in ("ruff.exe", "ruff"):
        cand = Path(sys.executable).with_name(name)
        if cand.is_file():
            return str(cand)
    return None


def lint_goals(root: Path) -> List[Dict[str, Any]]:
    """ruff findings that are real bugs (undefined names, shadowed defs). Needs ruff."""
    from core.agent.goal_quality import protected

    ruff = ruff_bin()
    if not ruff:
        return []
    try:
        proc = subprocess.run([ruff, "check", "core", "scripts", "gems", "--select", ",".join(LINT_RULES),
                               "--output-format", "json", "--exit-zero", "--no-cache"],
                              cwd=str(root), capture_output=True, text=True, timeout=60)
        rows = json.loads(proc.stdout or "[]")
    except Exception:
        return []
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        rel = os.path.relpath(r.get("filename") or "", str(root)).replace("\\", "/")
        if protected(rel) or Path(rel).name.startswith("_"):
            continue
        line = int((r.get("location") or {}).get("row") or 0)
        symbol = _enclosing(Path(root) / rel, line)
        if not symbol or "." in symbol and r.get("code") == "F811":
            continue
        gid = f"lint_{r.get('code')}_{Path(rel).stem}_{symbol.replace('.', '_')}"[:80]
        row = out.setdefault(gid, {
            "id": gid, "kind": "lint", "rule": r.get("code"), "file": rel, "symbol": symbol,
            "error_kind": "NameError" if r.get("code") == "F821" else "Lint", "error": "",
        })
        row["error"] = (row["error"] + f"\nline {line}: {r.get('code')} {r.get('message')}").strip()[-600:]
    return list(out.values())


def lint_clear(root: Path, goal: Dict[str, Any]) -> bool:
    ruff = ruff_bin()
    if not ruff:
        return False
    try:
        proc = subprocess.run([ruff, "check", goal["file"], "--select", goal["rule"], "--output-format", "json",
                               "--exit-zero", "--no-cache"], cwd=str(root), capture_output=True, text=True, timeout=60)
        rows = json.loads(proc.stdout or "[]")
    except Exception:
        return False
    for r in rows:
        line = int((r.get("location") or {}).get("row") or 0)
        if _enclosing(Path(root) / goal["file"], line) == goal["symbol"]:
            return False
    return True


# ---------------------------------------------------------------- index

def load_index(root: Path) -> Dict[str, Any]:
    for rel in (INDEX, SEED):
        path = Path(root) / rel
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data.setdefault("goals", {})
                    data.setdefault("done", [])
                    data.setdefault("dropped", {})
                    data.setdefault("cursor", 0)
                    return data
            except Exception:
                pass
    return {"goals": {}, "done": [], "dropped": {}, "cursor": 0}


def save_index(root: Path, data: Dict[str, Any]) -> None:
    path = Path(root) / INDEX
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated"] = _now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def test_files(root: Path) -> List[str]:
    return sorted(p.relative_to(root).as_posix() for p in (Path(root) / "tests").glob("test_*.py"))


def scan(root: Path, n_files: int = 8, timeout: int = 240, files: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Shard: run the next n test files, refresh their goals. Resolved ones leave the index."""
    root = Path(root)
    data = load_index(root)
    all_files = test_files(root)
    if files is None:
        cur = int(data.get("cursor") or 0) % max(1, len(all_files))
        files = (all_files[cur:] + all_files[:cur])[:n_files]
        data["cursor"] = (cur + n_files) % max(1, len(all_files))
    files = list(files)
    res = run_pytest(root, files, timeout=timeout, sbfl=sbfl_enabled())
    goals = data["goals"]
    for gid in [g for g, row in goals.items() if row.get("test_file") in files and row.get("kind") == "fix_test"]:
        if res["status"].get(goals[gid].get("nodeid")) == "pass":
            goals.pop(gid)
    added = 0
    for nid, text in res["fail"].items():
        goal, reason = classify_failure(root, nid, text, res.get("spectra"))
        if goal is not None and not fits_reply(root, goal):
            goal, reason = None, "too_large"
        if goal is None:
            data["dropped"][nid] = reason
            continue
        data["dropped"].pop(nid, None)
        if goal["id"] not in goals and goal["id"] not in data["done"]:
            added += 1
        goal["tractability"] = tractability(root, goal)
        goals[goal["id"]] = {**goals.get(goal["id"], {}), **goal}
    if not data.get("lint_ts") or files and files[0] == all_files[0]:
        for goal in lint_goals(root):
            if goal["id"] not in data["done"]:
                goal["tractability"] = tractability(root, goal)
                goals.setdefault(goal["id"], goal)
        data["lint_ts"] = _now()
    save_index(root, data)
    return {"ok": True, "files": len(files), "failing": len(res["fail"]), "added": added,
            "goals": len(goals), "secs": res["secs"]}


def ranked(root: Path) -> List[Dict[str, Any]]:
    data = load_index(root)
    rows = [g for g in data["goals"].values() if g.get("id") not in data["done"]]
    tries = data.get("tries") or {}
    # Batch 3: SBFL can point many failing tests at one function. Failed tries on a
    # (file, symbol) count against every goal that targets it, so the 1650 does not
    # spend 20 attempts on one wrong suspect.
    by_target: Dict[tuple, int] = {}
    for g in data["goals"].values():
        key = (g.get("file"), g.get("symbol"))
        by_target[key] = by_target.get(key, 0) + int(tries.get(g.get("id"), 0))
    for g in rows:
        own = int(tries.get(g["id"], 0))
        shared = by_target.get((g.get("file"), g.get("symbol")), 0) - own
        g["_rank"] = float(g.get("tractability") or 0) - 0.2 * own - 0.1 * shared
        g["_target_tries"] = own + shared
    return sorted(rows, key=lambda g: (-g["_rank"], g["id"]))


MAX_TRIES = 3
MAX_TARGET_TRIES = 6


def next_real(root: Path, skip: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    data = load_index(root)
    tries = data.get("tries") or {}
    skip = set(skip)
    for g in ranked(root):
        if g["id"] in skip or int(tries.get(g["id"], 0)) >= MAX_TRIES:
            continue
        if g.get("targets") and not _multi_on():
            continue  # multi-place goal from a run with ETHER_MULTI_EDIT=1; skipped while it is off
        if g.get("via") == "sbfl" and int(g.get("_target_tries") or 0) >= MAX_TARGET_TRIES:
            continue
        if not (Path(root) / g["file"]).is_file() and not any(
                t.get("kind") == "new_file" for t in g.get("targets") or []):
            continue
        g.pop("_rank", None)
        g.pop("_target_tries", None)
        return g
    return None


def mark(root: Path, goal_id: str, kept: bool) -> None:
    data = load_index(root)
    if kept:
        if goal_id not in data["done"]:
            data["done"].append(goal_id)
        data["goals"].pop(goal_id, None)
    else:
        tries = data.setdefault("tries", {})
        tries[goal_id] = int(tries.get(goal_id, 0)) + 1
    save_index(root, data)


# ---------------------------------------------------------------- prompt + edit

def _func_source(path: Path, symbol: str) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
    except Exception:
        return ""
    span = _span(tree, symbol) or (_assign_span(tree, symbol) if "." not in symbol else None)
    if not span:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[span[0] - 1: span[1]])


def _span(tree: ast.Module, symbol: str) -> Optional[tuple]:
    parts = symbol.split(".")
    body = tree.body
    node = None
    for i, name in enumerate(parts):
        node = next((n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                     and n.name == name), None)
        if node is None:
            return None
        body = getattr(node, "body", [])
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return start, node.end_lineno


def _test_source(root: Path, nodeid: str) -> str:
    rel, _, rest = nodeid.partition("::")
    name = rest.split("::")[-1].split("[")[0]
    src = _func_source(Path(root) / rel, name)
    if not src and "::" in rest:
        src = _func_source(Path(root) / rel, rest.replace("::", ".").split("[")[0])
    return src


EXEMPLAR_HEAD = "A different fix that passed this repo's tests before"


def build_prompt(root: Path, goal: Dict[str, Any], behaviour: Any = None, feedback: str = "",
                 exemplar: Optional[List[Dict[str, Any]]] = None) -> str:
    """Error + test + file-local slice. Never the answer. Capped by the model's context."""
    from core.kernel.context_budget import context_char_budget, slice_to_budget

    budget = context_char_budget()
    root = Path(root)
    name = goal["symbol"].split(".")[-1]
    head = (f"Goal: make {goal.get('nodeid') or goal.get('rule')} pass by editing {goal['file']}.\n"
            f"Error ({goal.get('error_kind')}):\n{str(goal.get('error') or '')[-500:]}\n")
    test = _test_source(root, goal["nodeid"])[:1400] if goal.get("nodeid") else ""
    use_ctx = getattr(behaviour, "use_workspace_context", True)
    current = _func_source(root / goal["file"], goal["symbol"]) if use_ctx else ""
    if goal.get("span"):
        from core.agent import span_edit

        current = span_edit.context_block(root, goal, bare=not use_ctx)
        tail = span_edit.prompt_tail(goal)
    elif goal.get("symbol_kind") == "assign":
        tail = (f"Reply with the complete new module-level assignment `{name} = ...` (no markdown). "
                "It replaces the current one.\n")
    else:
        tail = (f"Reply with one complete Python function `def {name}(...)` (no class wrapper, no markdown). "
                f"It replaces the current one" + (" in its class" if "." in goal["symbol"] else "")
                + ("; it is missing, so it is added." if goal.get("missing") else ".") + "\n")
        if constants_enabled() and "." not in goal["symbol"]:
            tail += ("If the fix also needs a module-level constant changed, add the complete new "
                     "`NAME = ...` line(s) before the function.\n")
    addon = (getattr(behaviour, "prompt_addon", "") or "") + "\n" if behaviour is not None else ""
    parts = [head]
    if test:
        parts.append(f"Test:\n{test}\n")
    if feedback:
        parts.append(f"Your last try failed:\n{feedback[-400:]}\n")
    if exemplar and getattr(behaviour, "use_exemplars", False):
        from core.agent import exemplars as _ex  # batch 7: one gate-kept diff, never this goal's

        # The code context (span window / target function) keeps its room; the hint takes what is left.
        keep = min(len(current or ""), budget // 2) if (use_ctx or goal.get("span")) else 0
        hint = _ex.block(exemplar, budget - sum(len(p) for p in parts) - len(tail) - len(addon) - keep - 40)
        if hint:
            parts.append(hint)
    fixed = sum(len(p) for p in parts) + len(tail) + len(addon) + 40
    room = max(200, budget - fixed)
    if use_ctx or goal.get("span"):
        body = (root / goal["file"]).read_text(encoding="utf-8", errors="ignore")
        if use_ctx and getattr(behaviour, "force_repo_map", False):
            sig = "\n".join(l for l in body.splitlines() if l.startswith(("def ", "class ", "import ", "from ")))
            ctx = (sig + "\n\n" + current)[-room:] if current else slice_to_budget(sig, query=name, cap=room)
        elif goal.get("span"):
            ctx = current[-room:]
        elif current and len(current) <= room:
            ctx = current
            consts = _constants_used(root / goal["file"], current) if constants_enabled() else ""
            if consts and len(consts) + len(current) + 2 <= room:
                ctx = consts + "\n\n" + current
        else:
            ctx = slice_to_budget(body, query=name, cap=room)
        parts.append(f"{goal['file']} (current):\n{ctx}\n")
    prompt = "".join(parts) + addon + tail
    return prompt[:budget]


def extract_function(reply: str, symbol: str) -> str:
    name = symbol.split(".")[-1]
    text = (reply or "").replace("\r\n", "\n")
    text = re.sub(r"```(?:python)?", "", text)
    m = re.search(rf"^([ \t]*)(?:async\s+)?def {re.escape(name)}\s*\(", text, re.M)
    if not m:
        return ""
    lines = text[m.start():].split("\n")
    indent = len(m.group(1).expandtabs())
    out = [lines[0][indent:]]
    for line in lines[1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent and not line.lstrip().startswith(("#", ")")):
            break
        out.append(line[indent:] if len(line) >= indent else line.strip())
    fn = "\n".join(out).rstrip() + "\n"
    try:
        tree = ast.parse(fn)
    except SyntaxError:
        return ""
    if not tree.body or not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    return fn


def apply_function(root: Path, goal: Dict[str, Any], fn: str, write: bool = True,
                   base: Optional[str] = None) -> Dict[str, Any]:
    """Replace (or add) one function. The file must still parse. Returns the original for revert."""
    path = Path(root) / goal["file"]
    original = base if base is not None else path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(original)
    except SyntaxError:
        return {"ok": False, "reason": "target does not parse"}
    lines = original.splitlines()
    span = _span(tree, goal["symbol"])
    if span:
        first = lines[span[0] - 1]
        indent = first[: len(first) - len(first.lstrip())]
        new_fn = "\n".join((indent + l) if l.strip() else l for l in fn.rstrip("\n").split("\n"))
        new = "\n".join(lines[: span[0] - 1] + new_fn.split("\n") + lines[span[1]:]) + "\n"
    elif "." in goal["symbol"]:
        return {"ok": False, "reason": "method not found"}
    else:
        new = original.rstrip() + "\n\n\n" + fn
    if new == original:
        return {"ok": False, "reason": "no change"}
    try:
        compile(new, str(path), "exec")
    except SyntaxError as exc:
        return {"ok": False, "reason": f"syntax: {exc.msg}"}
    if not write:
        return {"ok": True, "original": original, "new": new}
    path.write_text(new, encoding="utf-8")
    return {"ok": True, "original": original}


def _constants_used(path: Path, func_src: str) -> str:
    """Current source of the module-level assignments the function reads (context, not an answer)."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
        used = {n.id for n in ast.walk(ast.parse(textwrap_dedent(func_src))) if isinstance(n, ast.Name)}
    except Exception:
        return ""
    lines = text.splitlines()
    out = []
    for node in tree.body:
        names = _assign_names(node)
        if names and set(names) & used and (node.end_lineno or node.lineno) - node.lineno < MAX_ASSIGN_LINES:
            out.append("\n".join(lines[node.lineno - 1: node.end_lineno]))
    return "\n".join(out[:MAX_ASSIGNS])


def textwrap_dedent(src: str) -> str:
    import textwrap

    return textwrap.dedent(src)


def extract_assigns(reply: str) -> Dict[str, str]:
    """Top-level `NAME = ...` / `NAME: T = ...` statements in a reply, by name (last wins)."""
    text = re.sub(r"```(?:python)?", "", (reply or "").replace("\r\n", "\n"))
    lines = text.split("\n")
    out: Dict[str, str] = {}
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=(?!=)", lines[i])
        if not m:
            i += 1
            continue
        for j in range(i, min(len(lines), i + MAX_ASSIGN_LINES)):
            chunk = "\n".join(lines[i: j + 1])
            try:
                tree = ast.parse(chunk)
            except SyntaxError:
                continue
            if len(tree.body) == 1 and _assign_names(tree.body[0]) == [m.group(1)]:
                if not m.group(1).startswith("__"):
                    out[m.group(1)] = chunk.rstrip() + "\n"
                i = j
                break
        i += 1
    return out


def extract_edit(reply: str, goal: Dict[str, Any]) -> Dict[str, Any]:
    """{"function": src or "", "assigns": {name: src}} from a model reply. Empty = nothing usable."""
    if goal.get("span"):
        from core.agent import span_edit

        return {"function": "", "assigns": {}, "span": span_edit.extract(reply)}
    if goal.get("symbol_kind") == "assign":
        assigns = extract_assigns(reply) if constants_enabled() else {}
        if goal["symbol"] not in assigns:
            return {"function": "", "assigns": {}}
        return {"function": "", "assigns": assigns}
    fn = extract_function(reply, goal["symbol"])
    if not fn:
        return {"function": "", "assigns": {}}
    assigns = extract_assigns(reply) if constants_enabled() and "." not in goal["symbol"] else {}
    assigns.pop(goal["symbol"].split(".")[-1], None)
    return {"function": fn, "assigns": assigns}


def apply_edit(root: Path, goal: Dict[str, Any], edit: Dict[str, Any]) -> Dict[str, Any]:
    """Function replace/add plus module-level assignment replace/add, in one compiled write.

    Allowed assignments: names already bound at module level in the target file, or
    names the new function reads (added just before it). At most MAX_ASSIGNS, none
    dunder, each < MAX_ASSIGN_LINES. The target must not be protected."""
    from core.agent.goal_quality import protected

    if protected(goal.get("file", "")):
        return {"ok": False, "reason": "protected path"}
    if goal.get("span"):
        from core.agent import span_edit

        return span_edit.apply(root, goal, edit.get("span") or "")
    path = Path(root) / goal["file"]
    original = path.read_text(encoding="utf-8")
    assigns = dict(edit.get("assigns") or {})
    fn = edit.get("function") or ""
    if not fn and not assigns:
        return {"ok": False, "reason": "empty edit"}
    if len(assigns) > MAX_ASSIGNS:
        return {"ok": False, "reason": f"too many assignments ({len(assigns)} > {MAX_ASSIGNS})"}
    if fn:
        res = apply_function(root, goal, fn, write=False, base=original)
        if not res.get("ok") and not (assigns and res.get("reason") == "no change"):
            return res
        text = res.get("new") or original
    else:
        text = original
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"ok": False, "reason": "target does not parse"}
    used = set()
    if fn:
        used = {n.id for n in ast.walk(ast.parse(fn)) if isinstance(n, ast.Name)}
    lines = text.splitlines()
    added: List[str] = []
    for name in sorted(assigns, key=lambda n: -((_assign_span(tree, n) or (0, 0))[0])):
        src = assigns[name].rstrip("\n").split("\n")
        span = _assign_span(tree, name)
        if span:
            lines = lines[: span[0] - 1] + src + lines[span[1]:]
        elif name in used or (goal.get("symbol_kind") == "assign" and name == goal["symbol"]):
            added.append("\n".join(src))
        else:
            return {"ok": False, "reason": f"assignment {name} is new and not used by the edit"}
    new = "\n".join(lines) + "\n"
    if added:
        anchor = None
        if fn:
            t2 = ast.parse(new)
            span = _span(t2, goal["symbol"])
            anchor = span[0] if span else None
        block = "\n".join(added)
        nl = new.splitlines()
        if anchor:
            new = "\n".join(nl[: anchor - 1] + block.split("\n") + ["", ""] + nl[anchor - 1:]) + "\n"
        else:
            new = new.rstrip() + "\n\n" + block + "\n"
    if new == original:
        return {"ok": False, "reason": "no change"}
    try:
        compile(new, str(path), "exec")
    except SyntaxError as exc:
        return {"ok": False, "reason": f"syntax: {exc.msg}"}
    path.write_text(new, encoding="utf-8")
    return {"ok": True, "original": original, "assigns": sorted(assigns), "function": bool(fn)}


# ---------------------------------------------------------------- regression guard

SMOKE = ("tests/test_ether_batch1_ladder.py", "tests/test_batch2_goal_source.py")
MAX_AFFECTED = 6


def affected_tests(root: Path, rel: str, limit: int = MAX_AFFECTED) -> List[str]:
    """Test files that import the edited module (by dotted name), smallest first."""
    mod = rel[:-3].replace("/", ".")
    pat = re.compile(rf"(from {re.escape(mod)} import|import {re.escape(mod)}\b)")
    hits = []
    for t in test_files(root):
        try:
            if pat.search((Path(root) / t).read_text(encoding="utf-8", errors="ignore")):
                hits.append(t)
        except Exception:
            continue
    hits.sort(key=lambda t: (Path(root) / t).stat().st_size)
    return hits[:limit]


# Batch 9 (audit W5): the guard ran the target file + <= 6 direct importers + 2 smoke files
# (36-79 of 1,947 tests). It now also runs tests that import a module importing the target
# (transitively, ETHER_GUARD_DEPTH levels), plus a fixed per-goal random sample of small test
# files, inside a file budget sized for the 1650 (each gate run stays under ETHER_GATE_TIMEOUT_S;
# a run that does not finish aborts the attempt). ETHER_GUARD_TRANSITIVE=0 = batch 8 selection.
_IMPORT_RE = re.compile(r"^[ \t]*(?:from[ \t]+([\w.]+)[ \t]+import[ \t]+\(?([\w ,\t*]+)|import[ \t]+([\w., \t]+))", re.M)
_GRAPH_CACHE: Dict[str, Any] = {}


def _guard_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _imports_of(text: str) -> set:
    out = set()
    for frm, names, plain in _IMPORT_RE.findall(text):
        if frm:
            out.add(frm)
            for n in names.replace("(", " ").split(","):
                n = n.strip().split(" ")[0]
                if n and n != "*":
                    out.add(f"{frm}.{n}")
        else:
            for n in plain.split(","):
                n = n.strip().split(" ")[0]
                if n:
                    out.add(n)
    return out


def _dotted(rel: str) -> str:
    mod = rel[:-3].replace("/", ".")
    return mod[: -len(".__init__")] if mod.endswith(".__init__") else mod


def import_graph(root: Path) -> Dict[str, set]:
    """{module: repo modules it imports}, non-test code only; cached on the tree's .py stats."""
    root = Path(root)
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".") and d != "tests"]
        for f in filenames:
            if f.endswith(".py"):
                files.append(os.path.join(dirpath, f))
    sig_parts = []
    for f in files:
        try:
            st = os.stat(f)
            sig_parts.append((f, st.st_size, st.st_mtime_ns))
        except OSError:
            continue
    sig = hashlib.sha1(repr(sorted(sig_parts)).encode("utf-8")).hexdigest()
    hit = _GRAPH_CACHE.get(str(root))
    if hit and hit[0] == sig:
        return hit[1]
    mods = {_dotted(Path(f).relative_to(root).as_posix()): f for f, _, _ in sig_parts}
    graph: Dict[str, set] = {}
    for mod, f in mods.items():
        try:
            text = Path(f).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        graph[mod] = {m for m in _imports_of(text) if m in mods and m != mod}
    _GRAPH_CACHE[str(root)] = (sig, graph)
    return graph


def importer_closure(root: Path, rel: str, depth: int) -> Dict[str, int]:
    """{module: distance} for the target and every module importing it within `depth` hops."""
    graph = import_graph(root)
    rev: Dict[str, set] = {}
    for mod, deps in graph.items():
        for d in deps:
            rev.setdefault(d, set()).add(mod)
    start = _dotted(rel)
    dist = {start: 0}
    frontier = [start]
    for level in range(1, depth + 1):
        nxt = []
        for m in frontier:
            for imp in rev.get(m, ()):
                if imp not in dist:
                    dist[imp] = level
                    nxt.append(imp)
        frontier = nxt
    return dist


def transitive_tests(root: Path, rel: str, limit: int, depth: int) -> List[str]:
    dist = importer_closure(root, rel, depth)
    scored = []
    for t in test_files(root):
        try:
            names = _imports_of((Path(root) / t).read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        hit = [dist[n] for n in names if n in dist]
        if hit:
            scored.append((min(hit), (Path(root) / t).stat().st_size, t))
    scored.sort()
    return [t for _, _, t in scored[:limit]]


def sample_tests(root: Path, goal: Dict[str, Any], k: int, exclude: Iterable[str]) -> List[str]:
    """A fixed random sample: same goal, same files (seeded by the goal id), small files only."""
    if k <= 0:
        return []
    cap = _guard_int("ETHER_GUARD_SAMPLE_MAX_BYTES", 24000)
    skip = set(exclude)
    seed = str(goal.get("id") or goal.get("file") or "")
    pool = []
    for t in test_files(root):
        if t in skip:
            continue
        try:
            if (Path(root) / t).stat().st_size > cap:
                continue
        except OSError:
            continue
        pool.append((hashlib.sha1(f"{seed}|{t}".encode("utf-8")).hexdigest(), t))
    return [t for _, t in sorted(pool)[:k]]


def guard_suite(root: Path, goal: Dict[str, Any]) -> List[str]:
    files = []
    if goal.get("test_file"):
        files.append(goal["test_file"])
    if os.getenv("ETHER_GUARD_TRANSITIVE", "1") == "0":
        files += [t for t in affected_tests(root, goal["file"]) if t not in files]
    else:
        limit = _guard_int("ETHER_GUARD_MAX_AFFECTED", 10)
        depth = _guard_int("ETHER_GUARD_DEPTH", 2)
        direct = affected_tests(root, goal["file"])
        files += [t for t in direct if t not in files]
        files += [t for t in transitive_tests(root, goal["file"], limit, depth) if t not in files][: max(0, limit - len(direct))]
    files += [t for t in SMOKE if (Path(root) / t).is_file() and t not in files]
    if os.getenv("ETHER_GUARD_TRANSITIVE", "1") != "0":
        files += sample_tests(root, goal, _guard_int("ETHER_GUARD_SAMPLE", 3), files)
    if os.getenv("ETHER_GUARD_SUITE") == "full":
        files = ["tests"]
    return files


def regressions(before: Dict[str, str], after: Dict[str, str]) -> List[str]:
    return sorted(n for n, s in before.items() if s == "pass" and after.get(n) not in ("pass", "skip"))


def siblings(root: Path, goal: Dict[str, Any]) -> List[str]:
    """Other open failing tests in the same test file that target the same symbol.

    Batch 3: a cheat `heartbeat_plan` passed its one target test while the stronger
    contract tests in the same file still failed; they had failed before, so the
    regression guard saw nothing. An edit to a symbol is now judged against every
    known failing test of that file on that symbol."""
    if goal.get("kind") != "fix_test":
        return []
    data = load_index(root)
    return sorted(g["nodeid"] for g in data["goals"].values()
                  if g.get("kind") == "fix_test" and g.get("file") == goal.get("file")
                  and g.get("symbol") == goal.get("symbol") and g.get("test_file") == goal.get("test_file")
                  and g.get("nodeid") != goal.get("nodeid") and g.get("id") not in data["done"])


def gate(root: Path, goal: Dict[str, Any], baseline: Dict[str, str], suite: List[str],
         base_tamper: Optional[List[str]] = None) -> Dict[str, Any]:
    """Target (and its siblings) pass and nothing that passed before fails now.

    Batch 9: an empty baseline, a timed-out / empty after-run, or a run that tampered with the
    sandbox copy beyond what the baseline run did is never a pass (`abort` / `tamper` say why)."""
    if not baseline:
        return {"ok": False, "target_ok": False, "regressions": [], "n_regressions": 0, "suite_n": 0, "secs": 0.0,
                "target_pass": False, "siblings": 0, "siblings_failing": [], "tail": "", "abort": "empty baseline"}
    res = run_pytest(root, suite)
    after = res["status"]
    why = ""
    if res.get("timeout") or res.get("rc") == -9:
        why = "after-run timeout"
    elif res.get("sandbox_error"):
        why = "sandbox error"
    elif not after:
        why = "after-run produced no test results"
    if why:
        return {"ok": False, "target_ok": False, "regressions": [], "n_regressions": 0, "suite_n": 0,
                "secs": res.get("secs", 0.0), "target_pass": False, "siblings": 0, "siblings_failing": [],
                "tail": why, "abort": why}
    goal_files = {goal.get("file") or ""} | {t.get("file") for t in (goal.get("targets") or []) if isinstance(t, dict)}
    new_tamper = sorted(set(res.get("tamper") or []) - set(base_tamper or []) - goal_files)
    sibs = [n for n in siblings(root, goal) if n in after]
    sib_fail = [n for n in sibs if after.get(n) not in ("pass", "skip")]
    if goal.get("kind") == "lint":
        target_ok = lint_clear(root, goal) and any(s == "pass" for s in after.values())
    else:
        target_ok = after.get(goal["nodeid"]) == "pass" and not sib_fail
    regs = regressions(baseline, after)
    tail = res["fail"].get(goal.get("nodeid") or "", "") or (res["fail"].get(sib_fail[0], "") if sib_fail else "")
    if new_tamper:
        return {"ok": False, "target_ok": bool(target_ok), "regressions": regs[:20], "n_regressions": len(regs),
                "suite_n": len(after), "secs": res["secs"], "target_pass": after.get(goal.get("nodeid") or "") == "pass",
                "siblings": len(sibs), "siblings_failing": sib_fail[:5], "outside": new_tamper[:10],
                "tail": "the test run changed " + ", ".join(new_tamper[:3])}
    return {"ok": bool(target_ok and not regs), "target_ok": bool(target_ok), "regressions": regs[:20],
            "n_regressions": len(regs), "suite_n": len(after), "secs": res["secs"],
            "target_pass": after.get(goal.get("nodeid") or "") == "pass",
            "siblings": len(sibs), "siblings_failing": sib_fail[:5], "tail": (tail or "")[-400:]}
