"""Batch 4 SBFL benchmark: Ochiai (batch 3) vs hub-aware rank (batch 4).

    python docs/results/batch4/sbfl_bench.py <repo> <tests_before.xml> <out.json> [n_mutants]

A. Live failures: run the failing test files once with the SBFL plugin on a scratch copy,
   classify every failure under both rankers, count goals per target.
B. Seeded mutants (ground truth): flip the first comparison / bump the first int constant /
   negate the first boolean return in a function that tests import, run the importing test
   files, and for every failing test that has no repo frame (the SBFL path) record the rank of
   the mutated function under both rankers (top-1, top-3, mean rank, abstain = below SBFL_MIN).
Everything runs on scratch copies; the repo is never written.
"""
import ast, json, os, random, re, shutil, sys, tempfile, time, xml.etree.ElementTree as ET
from pathlib import Path

src = Path(sys.argv[1]).resolve()
xmlp = Path(sys.argv[2]).resolve()
outp = Path(sys.argv[3]).resolve()
n_mut = int(sys.argv[4]) if len(sys.argv) > 4 else 40
scratch = Path(tempfile.mkdtemp(prefix="ether_sbfl4_")) / "repo"
shutil.copytree(src, scratch, ignore=shutil.ignore_patterns(".git", "out", "__pycache__", ".pytest_cache", "memory"))
os.chdir(scratch)
sys.path.insert(0, str(scratch))
from core.agent import goal_source as gs  # noqa: E402
from core.agent.fault_loc import ochiai, rank  # noqa: E402
from core.agent.goal_quality import protected  # noqa: E402

doc = {"source": "batch4 sbfl_bench", "ts": time.strftime("%Y-%m-%d %H:%M:%S %z")}

# ---------------- A. live failures
t = ET.parse(xmlp).getroot()
files = sorted({gs.nodeid_of(scratch, tc.get("classname") or "", tc.get("name") or "").split("::")[0]
                for tc in t.iter("testcase") if tc.find("failure") is not None or tc.find("error") is not None})
files = [f for f in files if (scratch / f).is_file()]
t0 = time.time()
res = gs.run_pytest(scratch, files, timeout=1800, sbfl=True)
live = {}
_fits = gs.fits_reply
for mode, gate in (("ochiai", False), ("hub", False), ("hub+size_gate", True)):
    os.environ["ETHER_SBFL_RANK"] = mode.split("+")[0]
    gs.fits_reply = _fits if gate else (lambda root, goal: True)
    vias, targets, reasons = {}, {}, {}
    sizes = []
    for nid, text in res["fail"].items():
        goal, reason = gs.classify_failure(scratch, nid, text, res.get("spectra"))
        if goal is not None and not gs.fits_reply(scratch, goal):
            goal, reason = None, "too_large"
        if goal is not None and not goal.get("missing"):
            sizes.append(gs.est_tokens(gs._func_source(scratch / goal["file"], goal["symbol"])))
        reasons[reason] = reasons.get(reason, 0) + 1
        if goal is None:
            continue
        vias[goal.get("via")] = vias.get(goal.get("via"), 0) + 1
        if goal.get("via") == "sbfl":
            k = goal["file"] + "::" + goal["symbol"]
            targets[k] = targets.get(k, 0) + 1
    top = max(targets.values()) if targets else 0
    live[mode] = {"failing": len(res["fail"]), "goals": sum(vias.values()), "vias": vias, "reasons": reasons,
                  "sbfl_targets": dict(sorted(targets.items(), key=lambda kv: -kv[1])),
                  "distinct_sbfl_targets": len(targets), "largest_target_share": round(top / max(1, sum(targets.values())), 3),
                  "targets_over_240_tokens": sum(1 for x in sizes if int(x * 1.1) > 240),
                  "targets_over_reply_max": sum(1 for x in sizes if int(x * 1.1) > gs.reply_max())}
gs.fits_reply = _fits
doc["live"] = live
doc["live_secs"] = round(time.time() - t0, 1)
os.environ.pop("ETHER_SBFL_RANK", None)

if n_mut == 0:
    prev = json.loads(outp.read_text(encoding="utf-8")) if outp.is_file() else {}
    doc["mutants"] = prev.get("mutants", {})
    outp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(doc["live"], indent=1))
    shutil.rmtree(scratch.parent, ignore_errors=True)
    sys.exit(0)

# ---------------- B. mutants
test_files = sorted(p.relative_to(scratch).as_posix() for p in (scratch / "tests").glob("test_*.py"))
imports = {}
for tf in test_files:
    text = (scratch / tf).read_text(encoding="utf-8", errors="ignore")
    for mod, names in re.findall(r"^from ((?:core|scripts)[\w.]*) import ([\w, ()]+)", text, re.M):
        for n in re.findall(r"\w+", names):
            imports.setdefault((mod.replace(".", "/") + ".py", n), set()).add(tf)
cands = []
for (rel, name), tfs in imports.items():
    p = scratch / rel
    if not p.is_file() or protected(rel) or rel.startswith("core/agent/fault_loc"):
        continue
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    node = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name), None)
    if node is None or not (3 <= (node.end_lineno - node.lineno) <= 60):
        continue
    cands.append((rel, name, sorted(tfs)[:3]))
cands.sort()
random.Random(4).shuffle(cands)


class Mut(ast.NodeTransformer):
    FLIP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE,
            ast.LtE: ast.Gt, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}

    def __init__(self):
        self.done = None

    def visit_Compare(self, node):
        if self.done is None and type(node.ops[0]) in self.FLIP:
            node.ops[0] = self.FLIP[type(node.ops[0])]()
            self.done = "flip_compare"
        return self.generic_visit(node)

    def visit_Constant(self, node):
        if self.done is None and type(node.value) is int and not isinstance(node.value, bool):
            self.done = "int_plus_one"
            return ast.copy_location(ast.Constant(node.value + 1), node)
        return node


def mutate(rel, name):
    p = scratch / rel
    text = p.read_text(encoding="utf-8")
    tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    m = Mut()
    new_body = [m.visit(st) for st in node.body]
    if m.done is None:
        return None, text
    node.body = new_body
    lines = text.splitlines(keepends=True)
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
    seg = ast.unparse(node)
    indent = " " * node.col_offset
    seg = "".join(indent + l + "\n" for l in seg.splitlines())
    p.write_text("".join(lines[:start - 1]) + seg + "".join(lines[node.end_lineno:]), encoding="utf-8")
    return m.done, text


base_status = {}
rows = []
tried = 0
for rel, name, tfs in cands:
    if len([r for r in rows if r["sbfl_tests"]]) >= n_mut or tried >= n_mut * 4:
        break
    tried += 1
    key = tuple(tfs)
    if key not in base_status:
        base_status[key] = gs.run_pytest(scratch, list(tfs), timeout=240)["status"]
    op, original = mutate(rel, name)
    if op is None:
        continue
    try:
        r = gs.run_pytest(scratch, list(tfs), timeout=240, sbfl=True)
    finally:
        (scratch / rel).write_text(original, encoding="utf-8")
    newly = [n for n, st in r["status"].items() if st == "fail" and base_status[key].get(n) == "pass"]
    sbfl_tests = [n for n in newly if not gs._repo_frames(scratch, r["fail"].get(n, ""))]
    per = []
    for nid in sbfl_tests:
        hint = r["fail"].get(nid, "") + "\n" + gs._test_source(scratch, nid)
        out = {}
        for mode, ranked in (("ochiai", ochiai(r.get("spectra"), nid)), ("hub", rank(r.get("spectra"), nid, hint))):
            keys = [(rl, q.split(".")[-1]) for s, o, rl, q in ranked if s >= gs.SBFL_MIN and not protected(rl)]
            pos = keys.index((rel, name)) + 1 if (rel, name) in keys else None
            out[mode] = pos
        per.append(out)
    rows.append({"target": f"{rel}::{name}", "op": op, "files": list(tfs), "newly_failing": len(newly),
                 "sbfl_tests": len(sbfl_tests), "ranks": per})


def agg(mode):
    pts = [p[mode] for r in rows for p in r["ranks"]]
    n = len(pts)
    if not n:
        return {}
    return {"n_tests": n, "top1": round(sum(1 for x in pts if x == 1) / n, 3),
            "top3": round(sum(1 for x in pts if x and x <= 3) / n, 3),
            "found": round(sum(1 for x in pts if x) / n, 3),
            "mean_rank_when_found": round(sum(x for x in pts if x) / max(1, sum(1 for x in pts if x)), 2)}


doc["mutants"] = {"tried": tried, "with_sbfl_tests": sum(1 for r in rows if r["sbfl_tests"]),
                  "ochiai": agg("ochiai"), "hub": agg("hub"), "rows": rows}
outp.parent.mkdir(parents=True, exist_ok=True)
outp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in doc.items() if k != "mutants"} | {"mutants": {k: v for k, v in doc["mutants"].items() if k != "rows"}}, indent=1))
shutil.rmtree(scratch.parent, ignore_errors=True)
