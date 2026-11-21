"""Batch 6: topology failures as refactor goals (scratch copy; never writes the repo).

    python docs/results/batch6/topology6.py <repo> <out.json>

1. Counts the sites behind the 3 failing topology tests (D1, D2 / D2-hard, D3) with the test
   file's own helpers, and splits D1 into line drift (same file+module as a pinned allowlist
   entry; a test-side re-pin) vs. truly new imports.
2. Runs the two batch-6 refactor strategies (dedent_snippet, state_writer) through the real
   refactor gate (refactor.attempt: guard suite before/after, revert on regression) on a
   scratch copy, then recounts D3 sites and re-runs tests/test_topology.py.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

src = Path(sys.argv[1]).resolve()
outp = Path(sys.argv[2]).resolve()
scratch = Path(tempfile.mkdtemp(prefix="ether_topo6_")) / "repo"
shutil.copytree(src, scratch, ignore=shutil.ignore_patterns(".git", "out", "__pycache__", ".pytest_cache", "memory"))
os.chdir(scratch)
sys.path[:0] = [str(scratch), str(scratch / "tests")]
os.environ["ETHER_ROOT"] = str(scratch)


def counts():
    import importlib

    import test_topology as T
    importlib.reload(T)
    d1 = set()
    for p in T._py_files("gems"):
        for line, mod, _ in T._imports(p):
            if mod.lstrip(".").split(".")[0] == "core" and not any(mod == ok or mod.startswith(ok + ".") for ok in T._D1_LEGAL):
                d1.add((T._rel(p), line, mod))
    d1_new = d1 - T.D1_ALLOWLIST
    pinned = {(f, m) for f, _, m in T.D1_ALLOWLIST}
    d2 = set()
    for p in T._py_files("core"):
        for line, mod, _ in T._imports(p):
            if T._is_gems(mod):
                d2.add((T._rel(p), line, mod))
    b = T.D2_SANCTIONED_GEM_BRIDGE
    d2_new = {s for s in d2 - T.D2_ALLOWLIST if (s[0], s[2]) != (b[0], b[1])}
    hard = []
    for p in list(T._py_files("core/loop", "core/spine")) + [T.REPO / "core" / "vectors.py"]:
        for line, mod, fn in T._imports(p):
            if T._is_gems(mod) and (T._rel(p), mod, fn) != b:
                hard.append((T._rel(p), line, mod))
    import ast
    unparsable, d3 = [], set()
    for p in T._py_files("cli", "core", "dashboard", "gems", "scripts", "tools"):
        rel = T._rel(p)
        if rel in T._D3_WRITER_MODULES:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError:
            unparsable.append(rel)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and T._is_write_call(node) and T._targets_state(node):
                d3.add((rel, node.lineno))
    return {"d1_new": len(d1_new), "d1_line_drift": sum(1 for f, _, m in d1_new if (f, m) in pinned),
            "d1_truly_new": sorted(f"{f}:{ln} {m}" for f, ln, m in d1_new if (f, m) not in pinned),
            "d2_new": len(d2_new), "d2_hard": len(hard),
            "d3_unparsable": unparsable, "d3_new_sites": sorted(f"{f}:{ln}" for f, ln in d3 - T.D3_ALLOWLIST)}


def topo_tests():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_topology.py"],
                       cwd=str(scratch), capture_output=True, text=True, timeout=600)
    return [ln.split(" ")[1] for ln in r.stdout.splitlines() if ln.startswith("FAILED")]


doc = {"source": "docs/results/batch6/topology6.py", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
doc["before"] = counts()
doc["before_failing"] = topo_tests()
from core.agent import refactor  # noqa: E402

rows = []
for strategy in ("dedent_snippet", "state_writer"):
    for goal in refactor.candidates(scratch, strategy):
        t0 = time.time()
        res = refactor.attempt(scratch, goal)
        rows.append({"strategy": strategy, "file": goal["file"], "kept": bool(res.get("ok")),
                     "note": res.get("note"), "suite_n": res.get("suite_n"), "secs": round(time.time() - t0, 1)})
        print(json.dumps(rows[-1]), flush=True)
doc["attempts"] = rows
doc["after"] = counts()
doc["after_failing"] = topo_tests()
outp.parent.mkdir(parents=True, exist_ok=True)
outp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in doc.items() if k != "attempts"}, indent=1))
shutil.rmtree(scratch.parent, ignore_errors=True)
