"""Refactor goals (flag ETHER_REFACTOR=1). Deterministic tool edits, kept by the gate.

Strategies (one bandit arm each, memory/learning/refactor_arms.json):
- remove_filler: delete zero-arg stubs that return a constant (describe() -> 'attach',
  add_name() -> 'add', ready() -> True, the count_defs() template) when nothing
  references them. They were added by the retired describe/ladder goals.
- dead_code: delete a private top-level function (`_name`) whose name appears
  nowhere else in the repo (vulture-style, AST + whole-repo name scan).
- ruff_safe: `ruff check --fix` with a safe rule set on one file (F401 outside
  __init__.py, F541, UP034). Skipped when ruff is not installed.
- dedent_snippet (batch 6): a .py file that does not parse but parses after
  textwrap.dedent (method bodies pasted at class indent, e.g. scripts/_obs_snippet.py).
  These break every AST scan over the tree (tests/test_topology.py D3).
- state_writer (batch 6): route a direct memory/ state write through the single-writer
  kernel (core/spine/state_io.py), equivalence-preserving rewrites only:
  `P.write_text(json.dumps(X, indent=2), encoding="utf-8")` -> `write_json(P, X)` (same
  JSON, indent 2, plus atomic replace and parent mkdir), and
  `str(X.relative_to(R)).replace("\\", "/")` -> `X.relative_to(R).as_posix()` (identical
  string for a Path; the `.replace` read as an atomic-rename write site). core/ and scripts/
  only: gems may not import core beyond the leaf contracts (D1). The gate also requires
  the site to be gone from the D3 detector.

Gate for every strategy: the file still compiles, every test in the guard suite
that passed before still passes (affected tests + smoke; ETHER_GUARD_SUITE=full runs
the whole suite), and at least one test ran. Otherwise the file is restored.
These are tool edits, not model edits: trajectories record policy="tool" and they
never count as model capability.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

STRATEGIES = ("remove_filler", "dead_code", "ruff_safe", "dedent_snippet", "state_writer")
STATE_HINTS = ("memory", "MEMORY", "vault", "ledger", "failure_graph", "GRAPH_PATH", "STATE_PATH", "curriculum",
               "runs", "quiz", "VAULT", "LEDGER", "GRAPH", "STATE")
STATE_WRITER_DIRS = ("core", "scripts")
FILLER_NAMES = frozenset({"describe", "add_name", "failing_test", "fits_name", "clamp_name", "ready", "count_defs"})
COUNT_DEFS_TEMPLATE = "max(1, len([line for line in open(__file__"
SCAN_DIRS = ("core", "scripts", "gems")
RUFF_SAFE = "F401,F541,UP034"


def enabled() -> bool:
    return os.getenv("ETHER_REFACTOR", "0") == "1"


def _py_files(root: Path, dirs: Iterable[str] = SCAN_DIRS) -> List[Path]:
    out: List[Path] = []
    for d in dirs:
        base = Path(root) / d
        if base.is_dir():
            out += [p for p in sorted(base.rglob("*.py")) if "_graveyard" not in p.parts and "__pycache__" not in p.parts]
    return out


def _protected(rel: str) -> bool:
    from core.agent.goal_quality import protected

    return protected(rel)


def is_filler(node: ast.AST, source: str) -> bool:
    if not isinstance(node, ast.FunctionDef) or node.name not in FILLER_NAMES:
        return False
    if node.args.args or node.args.kwonlyargs or node.args.vararg or node.args.kwarg or node.decorator_list:
        return False
    if len(node.body) != 1 or not isinstance(node.body[0], ast.Return):
        return False
    val = node.body[0].value
    if isinstance(val, ast.Constant):
        return True
    seg = ast.get_source_segment(source, val) or ""
    return node.name == "count_defs" and COUNT_DEFS_TEMPLATE in seg


class _Corpus:
    """All repo text once, for reference checks."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.files = {p.relative_to(self.root).as_posix(): p.read_text(encoding="utf-8", errors="ignore")
                      for p in _py_files(self.root, SCAN_DIRS + ("tests", "cli", "tools", "dashboard"))}

    def referenced(self, rel: str, name: str) -> bool:
        mod = rel[:-3].replace("/", ".")
        stem = mod.split(".")[-1]
        pats = [re.compile(rf"from {re.escape(mod)} import[^\n]*\b{re.escape(name)}\b"),
                re.compile(rf"\b{re.escape(stem)}\.{re.escape(name)}\b"),
                re.compile(rf"getattr\([^)]*['\"]{re.escape(name)}['\"]")]
        for other, text in self.files.items():
            if other == rel:
                continue
            if any(p.search(text) for p in pats):
                return True
        return False

    def name_count(self, name: str) -> int:
        if not hasattr(self, "_words"):
            from collections import Counter

            words: Counter = Counter()
            for t in self.files.values():
                words.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", t))
            self._words = words
        return int(self._words.get(name, 0))


def candidates(root: Path, strategy: Optional[str] = None) -> List[Dict[str, Any]]:
    root = Path(root)
    corpus = _Corpus(root)
    out: List[Dict[str, Any]] = []
    want = (strategy,) if strategy else STRATEGIES
    for path in _py_files(root):
        rel = path.relative_to(root).as_posix()
        if _protected(rel):
            continue
        text = corpus.files.get(rel) or path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            if "dedent_snippet" in want and dedent_fixes(text):
                out.append(_goal("dedent_snippet", rel, ""))
            continue
        if "state_writer" in want and rel.split("/")[0] in STATE_WRITER_DIRS and state_sites(tree):
            out.append(_goal("state_writer", rel, ""))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "remove_filler" in want and is_filler(node, text) and not corpus.referenced(rel, node.name):
                out.append(_goal("remove_filler", rel, node.name))
            elif ("dead_code" in want and node.name.startswith("_") and not node.name.startswith("__")
                  and not node.decorator_list and corpus.name_count(node.name) == 1):
                out.append(_goal("dead_code", rel, node.name))
    if "ruff_safe" in want and shutil.which("ruff"):
        out += [_goal("ruff_safe", rel, "") for rel in ruff_files(root)]
    return out


def _goal(strategy: str, rel: str, symbol: str) -> Dict[str, Any]:
    sym = symbol or "file"
    return {"id": f"refactor_{strategy}_{rel[:-3].replace('/', '_')}_{sym}"[:120], "kind": "refactor",
            "strategy": strategy, "file": rel, "symbol": symbol}


def ruff_files(root: Path) -> List[str]:
    try:
        proc = subprocess.run([shutil.which("ruff") or "ruff", "check", *SCAN_DIRS, "--select", RUFF_SAFE,
                               "--output-format", "json", "--exit-zero", "--no-cache"],
                              cwd=str(root), capture_output=True, text=True, timeout=60)
        rows = json.loads(proc.stdout or "[]")
    except Exception:
        return []
    files = set()
    for r in rows:
        rel = os.path.relpath(r.get("filename") or "", str(root)).replace("\\", "/")
        if r.get("fix") and not _protected(rel) and not (r.get("code") == "F401" and rel.endswith("__init__.py")):
            files.add(rel)
    return sorted(files)


def dedent_fixes(text: str) -> bool:
    import textwrap

    new = textwrap.dedent(text)
    if new == text:
        return False
    try:
        ast.parse(new)
    except SyntaxError:
        return False
    return True


def _hint(node: ast.AST) -> bool:
    dump = ast.dump(node)
    return any(h in dump for h in STATE_HINTS)


def _is_json_dumps(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "dumps"
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "json" and len(node.args) == 1)


def state_sites(tree: ast.Module) -> List[Dict[str, Any]]:
    """Rewritable direct state writes: [{"kind": "write_json"|"as_posix", "node": ...}], innermost first."""
    out: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "write_text"):
            call = node.value
            target = call.func.value
            if not isinstance(target, (ast.Name, ast.Attribute)) or not _hint(target):
                continue
            if len(call.args) != 1 or not _is_json_dumps(call.args[0]):
                continue
            dumps = call.args[0]
            kw = {k.arg: k.value for k in dumps.keywords}
            if set(kw) - {"indent"} or ("indent" in kw and not (isinstance(kw["indent"], ast.Constant)
                                                                and kw["indent"].value == 2)):
                continue
            enc = {k.arg: k.value for k in call.keywords}
            if set(enc) - {"encoding"} or ("encoding" in enc and not (isinstance(enc["encoding"], ast.Constant)
                                                                      and enc["encoding"].value in ("utf-8", "utf8"))):
                continue
            out.append({"kind": "write_json", "node": node, "target": target, "data": dumps.args[0]})
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "replace"
              and len(node.args) == 2 and all(isinstance(a, ast.Constant) for a in node.args)
              and [a.value for a in node.args] == ["\\", "/"] and isinstance(node.func.value, ast.Call)
              and isinstance(node.func.value.func, ast.Name) and node.func.value.func.id == "str"
              and len(node.func.value.args) == 1 and isinstance(node.func.value.args[0], ast.Call)
              and isinstance(node.func.value.args[0].func, ast.Attribute)
              and node.func.value.args[0].func.attr == "relative_to" and _hint(node)
              and node.lineno == node.end_lineno):
            out.append({"kind": "as_posix", "node": node, "path": node.func.value.args[0]})
    return out


def rewrite_state_writes(text: str) -> str:
    tree = ast.parse(text)
    lines = text.splitlines()
    sites = sorted(state_sites(tree), key=lambda s: (s["node"].lineno, s["node"].col_offset), reverse=True)
    for site in sites:
        node = site["node"]
        if site["kind"] == "write_json":
            first = lines[node.lineno - 1]
            ind = first[: len(first) - len(first.lstrip())]
            new = [ind + "from core.spine.state_io import write_json",
                   ind + f"write_json({ast.unparse(site['target'])}, {ast.unparse(site['data'])})"]
            lines[node.lineno - 1: node.end_lineno] = new
        else:
            ln = lines[node.lineno - 1]
            repl = ast.unparse(site["path"]) + ".as_posix()"
            lines[node.lineno - 1] = ln[: node.col_offset] + repl + ln[node.end_col_offset:]
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def remove_function(text: str, name: str) -> str:
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
            end = node.end_lineno or node.lineno
            keep = lines[:start] + lines[end:]
            out = "\n".join(keep)
            out = re.sub(r"\n{4,}", "\n\n\n", out).rstrip() + "\n"
            return out
    return text


def apply(root: Path, goal: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(root) / goal["file"]
    original = path.read_text(encoding="utf-8")
    if goal["strategy"] in ("remove_filler", "dead_code"):
        new = remove_function(original, goal["symbol"])
    elif goal["strategy"] == "dedent_snippet":
        import textwrap

        new = textwrap.dedent(original)
    elif goal["strategy"] == "state_writer":
        try:
            new = rewrite_state_writes(original)
        except SyntaxError:
            return {"ok": False, "reason": "target does not parse"}
    elif goal["strategy"] == "ruff_safe":
        rules = RUFF_SAFE if not goal["file"].endswith("__init__.py") else "F541,UP034"
        subprocess.run([shutil.which("ruff") or "ruff", "check", goal["file"], "--select", rules, "--fix",
                        "--no-cache", "--quiet"], cwd=str(root), capture_output=True, text=True, timeout=60)
        new = path.read_text(encoding="utf-8")
    else:
        return {"ok": False, "reason": "unknown strategy"}
    if new == original:
        path.write_text(original, encoding="utf-8")
        return {"ok": False, "reason": "no change"}
    try:
        compile(new, str(path), "exec")
    except SyntaxError as exc:
        path.write_text(original, encoding="utf-8")
        return {"ok": False, "reason": f"syntax: {exc.msg}"}
    if goal["strategy"] == "state_writer" and state_sites(ast.parse(new)):
        return {"ok": False, "reason": "state write site still present"}
    path.write_text(new, encoding="utf-8")
    return {"ok": True, "original": original, "removed": len(original.splitlines()) - len(new.splitlines())}


# ---------------------------------------------------------------- strategy arms

def arms_path(root: Path) -> Path:
    return Path(root) / "memory" / "learning" / "refactor_arms.json"


def arms(root: Path) -> Dict[str, Dict[str, int]]:
    try:
        data = json.loads(arms_path(root).read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return {s: {"pulls": int((data.get(s) or {}).get("pulls", 0)), "kept": int((data.get(s) or {}).get("kept", 0))}
            for s in STRATEGIES}


def credit(root: Path, strategy: str, kept: bool) -> Dict[str, Dict[str, int]]:
    table = arms(root)
    row = table.setdefault(strategy, {"pulls": 0, "kept": 0})
    row["pulls"] += 1
    row["kept"] += int(bool(kept))
    path = arms_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
    return table


def pick_strategy(root: Path, available: Iterable[str]) -> Optional[str]:
    """Optimistic mean (kept+1)/(pulls+2): untried strategies first, then the best keeper."""
    table = arms(root)
    avail = [s for s in STRATEGIES if s in set(available)]
    if not avail:
        return None
    return max(avail, key=lambda s: ((table[s]["kept"] + 1) / (table[s]["pulls"] + 2), -STRATEGIES.index(s)))


def _done(root: Path) -> set:
    try:
        return set(json.loads((Path(root) / "artifacts" / "refactor_done.json").read_text(encoding="utf-8")).get("ids") or [])
    except Exception:
        return set()


def _mark(root: Path, gid: str) -> None:
    done = _done(root)
    done.add(gid)
    path = Path(root) / "artifacts" / "refactor_done.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ids": sorted(done)}, indent=1) + "\n", encoding="utf-8")


def next_refactor(root: Path, skip: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    skip = set(skip) | _done(root)
    cands = [c for c in candidates(root) if c["id"] not in skip]
    strategy = pick_strategy(root, {c["strategy"] for c in cands})
    for c in cands:
        if c["strategy"] == strategy:
            return c
    return None


def attempt(root: Path, goal: Dict[str, Any], pick: Any = None) -> Dict[str, Any]:
    from core.agent import goal_source as gs

    root = Path(root)
    base = {"goal": goal["id"], "kind": "refactor", "file": goal["file"], "strategy": goal["strategy"],
            "policy": "tool"}
    suite = gs.guard_suite(root, {"file": goal["file"]})
    before = gs.run_pytest(root, suite)["status"]
    if not any(s == "pass" for s in before.values()):
        _mark(root, goal["id"])
        return {**base, "ok": False, "honest": True, "note": "rejected: no passing test covers it"}
    applied = apply(root, goal)
    if not applied.get("ok"):
        _mark(root, goal["id"])
        credit(root, goal["strategy"], False)
        return {**base, "ok": False, "honest": False, "note": "no edit: " + str(applied.get("reason"))}
    after = gs.run_pytest(root, suite)["status"]
    regs = gs.regressions(before, after)
    _mark(root, goal["id"])
    if regs:
        (root / goal["file"]).write_text(applied["original"], encoding="utf-8")
        credit(root, goal["strategy"], False)
        return {**base, "ok": False, "honest": False, "note": "regression", "regressions": len(regs),
                "caught": regs[:5]}
    credit(root, goal["strategy"], True)
    from core.agent.sota import remember

    remember(root, goal["id"], f"refactor kept, -{applied['removed']} lines, 0 regressions", kept=True, file=goal["file"])
    return {**base, "ok": True, "honest": True, "tests_ok": True, "regressions": 0, "suite_n": len(after),
            "removed_lines": applied["removed"]}
