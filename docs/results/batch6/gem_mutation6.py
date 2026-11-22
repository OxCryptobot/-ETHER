"""Batch 6 gem handler mutation bench (scratch copy only; never writes the repo).

    python docs/results/batch6/gem_mutation6.py <repo> <full_spectra.json> <out.json> [contract_file]

Mutants: every eligible site (batch-4/5 operators: flip the comparison / int + 1) inside each
registered gem handler's `execute` (the 8 gems behind GemRegistry.execute), plus the batch-5
D set definition (k = 0..3 on the 7 handlers the dispatcher reached) as a subset.

Tests per handler:
  before = the test node ids that called that handler in the full-suite spectrum and passed;
  after  = before + the contract file's tests (minus its 2 deliberate real-bug tests).
A mutant is killed when a selected test that passes on the clean scratch fails (or errors).
Localisation on killed mutants: every newly failing test is ranked with the spectra of that
run (frames ignored, like batch-5 D) under hub and b5; plus the host's own classifier
(goal_source.classify_failure: frames first) -> is its goal target the mutated method?
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

src = Path(sys.argv[1]).resolve()
full = Path(sys.argv[2]).resolve()
outp = Path(sys.argv[3]).resolve()
contract = sys.argv[4] if len(sys.argv) > 4 else "tests/test_gem_contracts.py"
sys.path.insert(0, str(src))
scratch = Path(tempfile.mkdtemp(prefix="ether_gm6_")) / "repo"
shutil.copytree(src, scratch, ignore=shutil.ignore_patterns(".git", "out", "__pycache__", ".pytest_cache", "memory"))
os.environ["ETHER_ROOT"] = str(scratch)

from core.agent import goal_source as gs  # noqa: E402
from core.agent.fault_loc import rank, rank5  # noqa: E402

HANDLERS = {
    "gems/clear_quartz/sandbox.py": "ClearQuartz.execute",
    "gems/rose_quartz/router.py": "RoseQuartz.execute",
    "gems/selenite/planner.py": "Selenite.execute",
    "gems/black_tourmaline/security.py": "BlackTourmaline.execute",
    "gems/labradorite/profiler.py": "Labradorite.execute",
    "gems/amethyst/evolution.py": "Amethyst.execute",
    "gems/grandidierite/extension.py": "Grandidierite.execute",
    "gems/citrine/memory.py": "Citrine.execute",
}
REAL_BUG_TESTS = {f"{contract}::test_grandidierite_generate_scaffolds_into_quarantine",
                  f"{contract}::test_rose_quartz_stream_empty_content_is_an_error"}


class Mut(ast.NodeTransformer):
    FLIP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE,
            ast.LtE: ast.Gt, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}

    def __init__(self, k):
        self.k, self.seen, self.done = k, 0, None

    def _hit(self):
        hit = self.done is None and self.seen == self.k
        self.seen += 1
        return hit

    def visit_Compare(self, node):
        if type(node.ops[0]) in self.FLIP and self.done is None and self._hit():
            node.ops[0] = self.FLIP[type(node.ops[0])]()
            self.done = "flip_compare"
        return self.generic_visit(node)

    def visit_Constant(self, node):
        if type(node.value) is int and not isinstance(node.value, bool) and self.done is None and self._hit():
            self.done = "int_plus_one"
            return ast.copy_location(ast.Constant(node.value + 1), node)
        return node


def find(tree, qual):
    body, node = tree.body, None
    for part in qual.split("."):
        node = next((n for n in body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == part), None)
        if node is None:
            return None
        body = node.body
    return node


def n_sites(rel, qual):
    node = find(ast.parse((scratch / rel).read_text(encoding="utf-8")), qual)
    m = Mut(10 ** 9)
    for st in node.body:
        m.visit(st)
    return m.seen


def mutate(rel, qual, k):
    p = scratch / rel
    text = p.read_text(encoding="utf-8")
    tree = ast.parse(text)
    node = find(tree, qual)
    m = Mut(k)
    new_body = [m.visit(st) for st in node.body]
    if m.done is None:
        return None, text
    node.body = new_body
    lines = text.splitlines(keepends=True)
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
    seg = "".join(" " * node.col_offset + ln + "\n" for ln in ast.unparse(node).splitlines())
    p.write_text("".join(lines[:start - 1]) + seg + "".join(lines[node.end_lineno:]), encoding="utf-8")
    return m.done, text


spec = json.loads(full.read_text(encoding="utf-8")).get("tests") or {}
cover = {rel: sorted(n for n, row in spec.items() if row.get("outcome") == "passed"
                     and any(q == qual and r == rel for r, q in row.get("calls") or []))
         for rel, qual in HANDLERS.items()}
contract_ids = []
if (scratch / contract).is_file():
    col = gs.run_pytest(scratch, [contract], timeout=600)
    contract_ids = sorted(n for n, st in col["status"].items() if st == "pass" and n not in REAL_BUG_TESTS)
D_SET = {r for r, q in HANDLERS.items() if q != "RoseQuartz.execute"}

t0 = time.time()
rows = []
for rel, qual in HANDLERS.items():
    sel = {"before": cover[rel], "after": cover[rel] + contract_ids}
    base = {}
    for phase, ids in sel.items():
        base[phase] = gs.run_pytest(scratch, ids, timeout=900)["status"] if ids else {}
    for k in range(n_sites(rel, qual)):
        op, original = mutate(rel, qual, k)
        if op is None:
            continue
        row = {"target": f"{rel}::{qual}", "k": k, "op": op, "d_set": rel in D_SET and k < 4}
        try:
            for phase, ids in sel.items():
                ids = [i for i in ids if base[phase].get(i) == "pass"]
                if not ids:
                    row[phase] = {"killed": False, "selected": 0}
                    continue
                r = gs.run_pytest(scratch, ids, timeout=900, sbfl=(phase == "after"))
                newly = [n for n in ids if r["status"].get(n, "fail") == "fail"]
                row[phase] = {"killed": bool(newly) or r.get("rc") == -9, "selected": len(ids), "newly": len(newly)}
                if phase == "after" and newly:
                    loc = []
                    for nid in newly:
                        text = r["fail"].get(nid, "")
                        spectra = r.get("spectra") or {}
                        ent = {}
                        for mode in ("hub", "b5"):
                            res = rank(spectra, nid, "") if mode == "hub" else rank5(spectra, nid, "", root=str(scratch), text=text)
                            keys = [(rl, q) for s, o, rl, q in res if s >= gs.SBFL_MIN]
                            ent[mode] = keys.index((rel, qual)) + 1 if (rel, qual) in keys else None
                        try:
                            goal, reason = gs.classify_failure(scratch, nid, text, spectra)
                        except Exception as e:  # noqa: BLE001
                            goal, reason = None, f"crash:{type(e).__name__}"
                        ent["host_goal"] = reason if goal is None else (goal.get("via") or "goal")
                        ent["host_target"] = None if goal is None else f"{goal.get('file')}::{goal.get('symbol')}"
                        ent["host_target_ok"] = bool(goal) and goal.get("file") == rel and \
                            str(goal.get("symbol") or "") in (qual, qual.split(".")[-1])
                        loc.append(ent)
                    row["loc"] = loc
        finally:
            (scratch / rel).write_text(original, encoding="utf-8")
        rows.append(row)
        print(json.dumps({k2: v for k2, v in row.items() if k2 != "loc"}), flush=True)


def agg(rs):
    n = len(rs)
    out = {"mutants": n}
    for phase in ("before", "after"):
        out[f"killed_{phase}"] = sum(1 for r in rs if r[phase]["killed"])
        out[f"kill_rate_{phase}"] = round(out[f"killed_{phase}"] / n, 3) if n else None
    pts = [e for r in rs for e in r.get("loc") or []]
    for mode in ("hub", "b5"):
        m = len(pts)
        out[f"{mode}_top1"] = round(sum(1 for e in pts if e[mode] == 1) / m, 3) if m else None
        out[f"{mode}_top3"] = round(sum(1 for e in pts if e[mode] and e[mode] <= 3) / m, 3) if m else None
    out["loc_tests"] = len(pts)
    out["host_target_ok"] = round(sum(1 for e in pts if e["host_target_ok"]) / len(pts), 3) if pts else None
    return out


doc = {"source": "docs/results/batch6/gem_mutation6.py", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
       "contract_tests": len(contract_ids), "secs": round(time.time() - t0, 1),
       "all": agg(rows), "d_set": agg([r for r in rows if r["d_set"]]),
       "per_handler": {q: agg([r for r in rows if r["target"].endswith(q)]) for q in HANDLERS.values()},
       "selected_before": {q: len(cover[r]) for r, q in HANDLERS.items()}, "rows": rows}
outp.parent.mkdir(parents=True, exist_ok=True)
outp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: doc[k] for k in ("all", "d_set", "per_handler")}, indent=1))
shutil.rmtree(scratch.parent, ignore_errors=True)
