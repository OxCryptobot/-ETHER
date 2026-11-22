"""Batch 9: planted-bug goals for when the real goal pool runs dry (audit W7, W10).

ETHER_PLANTED_GOALS=1 (default 0 = off). The real pool (failing tests + lint) is finite and ran
dry within hours; then the host learns nothing. A planted goal is a single-site, validated bug in
a *live* module (reachable from scripts/host_main.py / host_supervisor.py, not protected):

1. generate(): pick a live function that a test file imports, apply one mutation (comparison flip,
   +/- swap, and/or swap, int constant +1) in a scratch copy, and keep it only if some test that
   passes on the original fails on the mutant (validated by running the tests, never assumed).
2. attempt(): copy the tree to a scratch workspace outside the repo (tempdir/ether_planted/<id>,
   no .git, empty artifacts/ and memory/), plant the bug there, and run the normal honest gate
   (_attempt_real: tool edit + target test + 0 regressions) against the scratch root. The reward
   is recorded on the real root's bandit like any real goal.

Never published, never committed: the writer's tree is not touched (the scratch copy is not a git
repo and is not under the repo), the pool lives in memory/planted/pool.json (gitignored).
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import random
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

ENTRY = ("scripts.host_main", "scripts.host_supervisor")
POOL = "memory/planted/pool.json"
MAX_FN_LINES = 60
MAX_TRIES = 3
SCRATCH_SKIP = frozenset({".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache",
                          ".mypy_cache", ".ruff_cache", "edit_ws", "sota_ws", ".qdrant", "models", "memory",
                          "artifacts", "out", "build", "dist"})


def enabled() -> bool:
    return os.getenv("ETHER_PLANTED_GOALS", "0") == "1"


def budget() -> int:
    try:
        return max(1, int(os.getenv("ETHER_PLANTED_CANDIDATES", "4")))
    except ValueError:
        return 4


# ---------------------------------------------------------------- live code

def live_files(root: Path, entry: Tuple[str, ...] = ENTRY) -> Set[str]:
    """Repo files the writer imports directly or transitively (lazy imports included).

    Re-exports in package __init__ files are not followed: importing anything under core/ executes
    core/__init__.py, which imports the legacy pipeline/orchestrator, but the writer never calls
    into them. With that rule 145 files are live and 35 of the 56 failing-test seed goals target dead code
    (the audit measured 36); following __init__ re-exports would call 216 files live."""
    from core.agent import goal_source as gs

    graph = gs.import_graph(root)
    seen = {m for m in entry if m in graph}
    todo = list(seen)
    while todo:
        m = todo.pop()
        if gs.mod_rel(root, m).endswith("__init__.py"):
            continue
        for d in graph.get(m, ()):
            if d not in seen:
                seen.add(d)
                todo.append(d)
    out = set()
    for m in seen:
        rel = gs.mod_rel(root, m)
        if (Path(root) / rel).is_file():
            out.add(rel)
    return out


def live_only() -> bool:
    """ETHER_GOAL_LIVE_ONLY=1: real goals whose target the writer never imports are not attempted."""
    return os.getenv("ETHER_GOAL_LIVE_ONLY", "0") == "1"


# ---------------------------------------------------------------- mutations

def _same_line(*nodes: ast.AST) -> bool:
    lines = {getattr(n, "lineno", -1) for n in nodes} | {getattr(n, "end_lineno", -2) for n in nodes}
    return len(lines) == 1


SWAPS = {ast.Lt: ("<", "<="), ast.LtE: ("<=", "<"), ast.Gt: (">", ">="), ast.GtE: (">=", ">"),
         ast.Eq: ("==", "!="), ast.NotEq: ("!=", "=="), ast.Add: ("+", "-"), ast.Sub: ("-", "+"),
         ast.And: ("and", "or"), ast.Or: ("or", "and")}


def sites(src: str, fn: ast.FunctionDef) -> List[Dict[str, Any]]:
    """Single-line mutation sites inside one function: (line, start col, end col, old, new, op)."""
    lines = src.splitlines()
    out: List[Dict[str, Any]] = []

    def between(a: ast.AST, b: ast.AST, old: str, new: str, op: str) -> None:
        if not _same_line(a, b):
            return
        ln = a.lineno
        line = lines[ln - 1]
        s, e = a.end_col_offset, b.col_offset
        seg = line[s:e]
        if seg.strip() != old:
            return
        i = s + seg.index(old)
        out.append({"line": ln, "col": i, "end": i + len(old), "old": old, "new": new, "op": op})

    for node in ast.walk(fn):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in SWAPS:
            old, new = SWAPS[type(node.ops[0])]
            between(node.left, node.comparators[0], old, new, "compare")
        elif isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub):
            old, new = SWAPS[type(node.op)]
            between(node.left, node.right, old, new, "arith")
        elif isinstance(node, ast.BoolOp) and len(node.values) == 2:
            old, new = SWAPS[type(node.op)]
            between(node.values[0], node.values[1], old, new, "bool")
        elif isinstance(node, ast.Constant) and type(node.value) is int and _same_line(node) \
                and not isinstance(node.value, bool):
            line = lines[node.lineno - 1]
            if line[node.col_offset:node.end_col_offset] == str(node.value) and 0 <= node.value < 10_000:
                out.append({"line": node.lineno, "col": node.col_offset, "end": node.end_col_offset,
                            "old": str(node.value), "new": str(node.value + 1), "op": "const"})
    return out


def mutate(src: str, site: Dict[str, Any]) -> str:
    lines = src.splitlines(keepends=True)
    line = lines[site["line"] - 1]
    lines[site["line"] - 1] = line[: site["col"]] + site["new"] + line[site["end"]:]
    return "".join(lines)


def _functions(src: str) -> List[ast.FunctionDef]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    return [n for n in tree.body if isinstance(n, ast.FunctionDef)
            and (n.end_lineno or n.lineno) - n.lineno + 1 <= MAX_FN_LINES and not n.name.startswith("__")]


# ---------------------------------------------------------------- scratch workspace

def scratch_dir(root: Path, name: str = "work") -> Path:
    real = Path(root).resolve()
    key = hashlib.sha1(str(real).encode("utf-8")).hexdigest()[:12]
    base = Path(os.getenv("ETHER_PLANTED_DIR") or (Path(tempfile.gettempdir()) / "ether_planted")).resolve()
    d = base / key / name
    try:
        d.relative_to(real)
    except ValueError:
        return d
    raise ValueError("scratch inside the repo")


def scratch(root: Path, name: str = "work") -> Path:
    """Fresh-enough copy of the tree (incremental) with empty runtime state."""
    root = Path(root).resolve()
    dst = scratch_dir(root, name)
    dst.mkdir(parents=True, exist_ok=True)
    src_files: Dict[str, os.stat_result] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SCRATCH_SKIP]
        for f in filenames:
            if f.endswith((".pyc", ".pyo")):
                continue
            p = Path(dirpath) / f
            src_files[p.relative_to(root).as_posix()] = p.stat()
    for dirpath, dirnames, filenames in os.walk(dst):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__",)]
        for f in filenames:
            p = Path(dirpath) / f
            rel = p.relative_to(dst).as_posix()
            if rel not in src_files and not rel.endswith((".pyc", ".pyo")):
                p.unlink(missing_ok=True)
    for rel, st in src_files.items():
        t = dst / rel
        try:
            ts = t.stat()
            if ts.st_size == st.st_size and ts.st_mtime_ns == st.st_mtime_ns:
                continue
        except OSError:
            pass
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, t)
    for state in ("artifacts", "memory"):
        shutil.rmtree(dst / state, ignore_errors=True)
        (dst / state).mkdir(parents=True, exist_ok=True)
    return dst


# ---------------------------------------------------------------- pool

def _pool_path(root: Path) -> Path:
    return Path(root) / POOL


def load_pool(root: Path) -> Dict[str, Any]:
    try:
        data = json.loads(_pool_path(root).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("goals", {})
            data.setdefault("done", [])
            data.setdefault("tries", {})
            return data
    except Exception:
        pass
    return {"goals": {}, "done": [], "tries": {}}


def save_pool(root: Path, data: Dict[str, Any]) -> None:
    p = _pool_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def generate(root: Path, n: Optional[int] = None, rng: Optional[random.Random] = None,
             files: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Validate up to n candidate bugs; add the valid ones to the pool. Runs tests in a scratch copy."""
    from core.agent import goal_source as gs
    from core.agent.goal_quality import protected

    root = Path(root)
    n = budget() if n is None else n
    rng = rng or random.Random(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    pool = load_pool(root)
    known = set(pool["goals"]) | set(pool["done"])
    cands = sorted(files) if files is not None else sorted(f for f in live_files(root)
                                                           if not protected(f) and not f.startswith("tests/"))
    rng.shuffle(cands)
    made: List[Dict[str, Any]] = []
    checked = 0
    box: Optional[Path] = None
    for rel in cands:
        if checked >= n:
            break
        tests = gs.affected_tests(root, rel, limit=2)
        if not tests:
            continue
        src = (root / rel).read_text(encoding="utf-8", errors="ignore")
        options = [(fn, s) for fn in _functions(src) for s in sites(src, fn)]
        rng.shuffle(options)
        for fn, site in options[:1]:
            gid = f"planted_{Path(rel).stem}_{fn.name}_{site['op']}_{site['line']}"[:80]
            if gid in known:
                continue
            checked += 1
            if box is None:
                box = scratch(root, "gen")
            target = box / rel
            orig = target.read_text(encoding="utf-8", errors="ignore")
            if orig != src:
                continue
            base = gs.run_pytest(box, tests, sandbox=False, timeout=120)
            if gs.baseline_abort(base):
                continue
            target.write_text(mutate(src, site), encoding="utf-8")
            try:
                bad = gs.run_pytest(box, tests, sandbox=False, timeout=120)
            finally:
                target.write_text(orig, encoding="utf-8")
            if bad.get("timeout") or not bad.get("status"):
                continue
            killed = sorted(t for t, st in base["status"].items() if st == "pass" and bad["status"].get(t) == "fail")
            if not killed:
                continue
            nodeid = killed[0]
            text = bad["fail"].get(nodeid, "")
            goal = {"via": "planted", "planted": True, "id": gid, "kind": "fix_test", "nodeid": nodeid,
                    "test_file": nodeid.split("::", 1)[0], "file": rel, "symbol": fn.name, "missing": False,
                    "test_import": False, "error_kind": gs._kind(text), "error": (text or "").strip()[-700:],
                    "site": site, "orig_sha": _sha(src), "killed": killed[:10],
                    "created": datetime.now(timezone.utc).isoformat()}
            goal["tractability"] = gs.tractability(root, goal)
            pool["goals"][gid] = goal
            made.append(goal)
    if made:
        save_pool(root, pool)
    return made


def next_planted(root: Path) -> Optional[Dict[str, Any]]:
    pool = load_pool(root)
    changed = False
    for gid, g in sorted(pool["goals"].items(), key=lambda kv: (-float(kv[1].get("tractability") or 0), kv[0])):
        path = Path(root) / g["file"]
        cur = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
        if _sha(cur) != g.get("orig_sha") or int(pool["tries"].get(gid, 0)) >= MAX_TRIES:
            pool["goals"].pop(gid, None)  # code moved on, or tried enough: never retried
            changed = True
            continue
        if changed:
            save_pool(root, pool)
        return g
    if changed:
        save_pool(root, pool)
    return None


def mark(root: Path, gid: str, kept: bool) -> None:
    pool = load_pool(root)
    if kept:
        pool["goals"].pop(gid, None)
        if gid not in pool["done"]:
            pool["done"].append(gid)
            pool["done"] = pool["done"][-500:]
    else:
        pool["tries"][gid] = int(pool["tries"].get(gid, 0)) + 1
    save_pool(root, pool)


def attempt(root: Path, ask: Callable[..., str]) -> Dict[str, Any]:
    """One planted-goal attempt through the normal honest gate, in a scratch copy."""
    from core.agent import goal_source as gs
    from core.agent import sota

    root = Path(root)
    goal = next_planted(root)
    if goal is None:
        try:
            generate(root)
        except Exception as exc:
            return {"ok": False, "honest": True, "note": "queue empty", "planted": f"generate failed: {type(exc).__name__}"}
        goal = next_planted(root)
    if goal is None:
        return {"ok": False, "honest": True, "note": "queue empty", "planted": "none"}
    box = scratch(root, "work")
    (box / goal["file"]).write_text(mutate((root / goal["file"]).read_text(encoding="utf-8"), goal["site"]),
                                    encoding="utf-8")
    gs.save_index(box, {"goals": {goal["id"]: goal}, "done": [], "dropped": {}, "cursor": 0})
    try:
        from core.agent.outcome import choose, record

        pick = choose(root, goal=goal)
    except Exception:
        pick = None
    seen: Dict[str, str] = {}
    result = sota._attempt_real(box, sota._guard(ask, seen), goal, pick, seen)
    result["planted"] = True
    if result.get("note") != "already present":
        mark(root, goal["id"], kept=bool(result.get("ok")))
    if pick is not None:
        try:
            row = record(root, pick, result)
            result["learn"] = {"arm": pick.arm, "bucket": pick.bucket, "kind": row.get("kind"),
                               "reward": row.get("reward")}
        except Exception as exc:
            result["learn_error"] = type(exc).__name__
    return result
