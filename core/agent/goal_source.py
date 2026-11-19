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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enabled() -> bool:
    return os.getenv("ETHER_GOAL_SOURCE", "1") != "0"


# ---------------------------------------------------------------- pytest runner

def test_env(root: Path, state: Optional[Path] = None) -> Dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    env["ETHER_TEST_STATE_ROOT"] = str(state or Path(tempfile.mkdtemp(prefix="ether_state_")))
    env.pop("ETHER_SUPERVISOR", None)
    return env


def nodeid_of(root: Path, classname: str, name: str) -> str:
    parts = (classname or "").split(".")
    for cut in range(len(parts), 0, -1):
        rel = "/".join(parts[:cut]) + ".py"
        if (Path(root) / rel).is_file():
            rest = parts[cut:]
            return "::".join([rel, *rest, name])
    return f"{classname}::{name}"


def run_pytest(root: Path, args: List[str], timeout: int = 180) -> Dict[str, Any]:
    """Run pytest, return {nodeid: status} plus failure texts. Never writes the repo."""
    root = Path(root)
    tmp = Path(tempfile.mkdtemp(prefix="ether_pt_"))
    xml = tmp / "r.xml"
    argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short",
            "-o", "junit_family=xunit1", f"--junitxml={xml}", "--continue-on-collection-errors", *args]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=str(root), capture_output=True, text=True, timeout=timeout,
                              env=test_env(root, tmp / "state"))
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp, ignore_errors=True)
        return {"ok": False, "rc": -9, "status": {}, "fail": {}, "secs": round(time.monotonic() - t0, 1)}
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
    shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": rc == 0, "rc": rc, "status": status, "fail": fail, "secs": round(time.monotonic() - t0, 1)}


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


def goal_from_failure(root: Path, nodeid: str, text: str) -> Optional[Dict[str, Any]]:
    """One failing test -> one goal, or None when the failure is infra or untargetable."""
    from core.agent.goal_quality import protected

    root = Path(root)
    if any(m in (text or "") for m in INFRA):
        return None
    test_file = nodeid.split("::", 1)[0]
    target, line, missing = "", 0, ""
    m = IMPORT_NAME.search(text or "")
    if m:
        missing = m.group(1)
        rel = m.group(2).replace(".", "/") + ".py"
        if (root / rel).is_file():
            target = rel
    if not target:
        for fm in FRAME.finditer(text or ""):
            rel = fm.group(1).replace("\\", "/")
            if rel.startswith(str(root).replace("\\", "/")):
                rel = rel[len(str(root)) + 1:]
            if rel.startswith("/") or ":" in rel[:3] or ".." in rel.split("/"):
                continue
            if (root / rel).is_file() and not rel.startswith("tests/") and "site-packages" not in rel:
                target, line = rel, int(fm.group(2))
    if not target:
        target, symbol_hint = _target_from_test(root, nodeid)
        if target and symbol_hint:
            missing = ""
            return _goal(root, nodeid, test_file, target, symbol_hint, False, text, via="test_import")
    if not target or protected(target):
        return None
    symbol = missing or (_enclosing(root / target, line) if line else "")
    if not symbol:
        return None
    return _goal(root, nodeid, test_file, target, symbol, bool(missing), text, via="frame" if line else "import_error")


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
    """No repo frame: the first function the test imports from a non-protected module and calls."""
    from core.agent.goal_quality import protected

    src = _test_source(root, nodeid)
    rel_test = nodeid.split("::", 1)[0]
    try:
        module_src = (Path(root) / rel_test).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "", ""
    for text in (src, module_src):
        for m in re.finditer(r"from ([A-Za-z_][\w.]*) import ([\w, ]+)", text):
            rel = m.group(1).replace(".", "/") + ".py"
            if not (Path(root) / rel).is_file() or protected(rel):
                continue
            for name in [n.strip() for n in m.group(2).split(",") if n.strip()]:
                if re.search(rf"\b{re.escape(name)}\(", src) and _is_function(root, rel, name):
                    return rel, name
    return "", ""


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


def lint_goals(root: Path) -> List[Dict[str, Any]]:
    """ruff findings that are real bugs (undefined names, shadowed defs). Needs ruff."""
    from core.agent.goal_quality import protected

    ruff = shutil.which("ruff")
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
    ruff = shutil.which("ruff")
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
    res = run_pytest(root, files, timeout=timeout)
    goals = data["goals"]
    for gid in [g for g, row in goals.items() if row.get("test_file") in files and row.get("kind") == "fix_test"]:
        if res["status"].get(goals[gid].get("nodeid")) == "pass":
            goals.pop(gid)
    added = 0
    for nid, text in res["fail"].items():
        goal = goal_from_failure(root, nid, text)
        if goal is None:
            data["dropped"][nid] = "infra_or_untargetable"
            continue
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
    for g in rows:
        g["_rank"] = float(g.get("tractability") or 0) - 0.2 * int(tries.get(g["id"], 0))
    return sorted(rows, key=lambda g: (-g["_rank"], g["id"]))


MAX_TRIES = 3


def next_real(root: Path, skip: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    data = load_index(root)
    tries = data.get("tries") or {}
    skip = set(skip)
    for g in ranked(root):
        if g["id"] in skip or int(tries.get(g["id"], 0)) >= MAX_TRIES:
            continue
        if not (Path(root) / g["file"]).is_file():
            continue
        g.pop("_rank", None)
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
    span = _span(tree, symbol)
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


def build_prompt(root: Path, goal: Dict[str, Any], behaviour: Any = None, feedback: str = "") -> str:
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
    tail = (f"Reply with one complete Python function `def {name}(...)` (no class wrapper, no markdown). "
            f"It replaces the current one" + (" in its class" if "." in goal["symbol"] else "")
            + ("; it is missing, so it is added." if goal.get("missing") else ".") + "\n")
    addon = (getattr(behaviour, "prompt_addon", "") or "") + "\n" if behaviour is not None else ""
    parts = [head]
    if test:
        parts.append(f"Test:\n{test}\n")
    if feedback:
        parts.append(f"Your last try failed:\n{feedback[-400:]}\n")
    fixed = sum(len(p) for p in parts) + len(tail) + len(addon) + 40
    room = max(200, budget - fixed)
    if use_ctx:
        body = (root / goal["file"]).read_text(encoding="utf-8", errors="ignore")
        if getattr(behaviour, "force_repo_map", False):
            sig = "\n".join(l for l in body.splitlines() if l.startswith(("def ", "class ", "import ", "from ")))
            ctx = (sig + "\n\n" + current)[-room:] if current else slice_to_budget(sig, query=name, cap=room)
        elif current and len(current) <= room:
            ctx = current
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


def apply_function(root: Path, goal: Dict[str, Any], fn: str) -> Dict[str, Any]:
    """Replace (or add) one function. The file must still parse. Returns the original for revert."""
    path = Path(root) / goal["file"]
    original = path.read_text(encoding="utf-8")
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
    path.write_text(new, encoding="utf-8")
    return {"ok": True, "original": original}


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


def guard_suite(root: Path, goal: Dict[str, Any]) -> List[str]:
    files = []
    if goal.get("test_file"):
        files.append(goal["test_file"])
    files += [t for t in affected_tests(root, goal["file"]) if t not in files]
    files += [t for t in SMOKE if (Path(root) / t).is_file() and t not in files]
    if os.getenv("ETHER_GUARD_SUITE") == "full":
        files = ["tests"]
    return files


def regressions(before: Dict[str, str], after: Dict[str, str]) -> List[str]:
    return sorted(n for n, s in before.items() if s == "pass" and after.get(n) not in ("pass", "skip"))


def gate(root: Path, goal: Dict[str, Any], baseline: Dict[str, str], suite: List[str]) -> Dict[str, Any]:
    """Target passes and nothing that passed before fails now."""
    res = run_pytest(root, suite)
    after = res["status"]
    if goal.get("kind") == "lint":
        target_ok = lint_clear(root, goal) and any(s == "pass" for s in after.values())
    else:
        target_ok = after.get(goal["nodeid"]) == "pass"
    regs = regressions(baseline, after)
    return {"ok": bool(target_ok and not regs), "target_ok": bool(target_ok), "regressions": regs[:20],
            "n_regressions": len(regs), "suite_n": len(after), "secs": res["secs"],
            "tail": (res["fail"].get(goal.get("nodeid") or "", "") or "")[-400:]}
