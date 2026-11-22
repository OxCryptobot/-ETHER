"""Batch 5 SBFL benchmark: Ochiai (b3) vs hub rank (b4) vs dispatch+evidence rank (b5).

    python docs/results/batch5/sbfl_bench5.py <repo> <tests_before.xml> <out.json> [n_func] [n_meth] [full_spectra.json]

A. Live failures (production path, reply-size gate on): goals, vias, SBFL target
   concentration (largest share, GemRegistry.execute share, distinct targets) per ranker.
B. Injected bugs, ground truth. Same operators as batch 4 (flip first comparison / bump
   first int constant), two sets:
   F = top-level functions the tests import (batch-4 set, same seed, comparable);
   M = methods reached through a dispatcher or a handler class (gems/*, core/loop/handlers,
       Class.method), test files picked from a full-suite spectrum (who actually runs them).
   For every newly failing test with no repo frame (the SBFL path) the rank of the mutated
   symbol under each ranker: top-1, top-3, found, mean rank. Scratch copies only.
"""
import ast, json, os, random, re, shutil, sys, tempfile, time, xml.etree.ElementTree as ET
from pathlib import Path

src = Path(sys.argv[1]).resolve()
xmlp = Path(sys.argv[2]).resolve()
outp = Path(sys.argv[3]).resolve()
n_func = int(sys.argv[4]) if len(sys.argv) > 4 else 40
n_meth = int(sys.argv[5]) if len(sys.argv) > 5 else 30
full = Path(sys.argv[6]).resolve() if len(sys.argv) > 6 else None
scratch = Path(tempfile.mkdtemp(prefix="ether_sbfl5_")) / "repo"
shutil.copytree(src, scratch, ignore=shutil.ignore_patterns(".git", "out", "__pycache__", ".pytest_cache", "memory"))
os.chdir(scratch)
sys.path.insert(0, str(scratch))
from core.agent import goal_source as gs  # noqa: E402
from core.agent.fault_loc import ochiai, rank, rank5  # noqa: E402
from core.agent.goal_quality import protected  # noqa: E402

MODES = ("ochiai", "hub", "b5", "b5_fanout", "b5_noev")
doc = {"source": "batch5 sbfl_bench5", "ts": time.strftime("%Y-%m-%d %H:%M:%S %z")}


def ranked(mode, spectra, nid, text):
    hint = text + "\n" + gs._test_source(scratch, nid)
    if mode == "ochiai":
        return ochiai(spectra, nid)
    if mode == "hub":
        return rank(spectra, nid, hint)
    import core.agent.fault_loc as fl

    keep = fl.DISPATCH_FANOUT
    try:
        if mode == "b5_fanout":
            fl.DISPATCH_FANOUT = 6
        if mode == "b5_noev":  # dispatcher resolution only, no failure-text evidence
            return rank5(spectra, nid, hint, root=None, text="")
        return rank5(spectra, nid, hint, root=str(scratch), text=text)
    finally:
        fl.DISPATCH_FANOUT = keep


# ---------------- A. live failures (production classifier per ranker)
t = ET.parse(xmlp).getroot()
files = sorted({gs.nodeid_of(scratch, tc.get("classname") or "", tc.get("name") or "").split("::")[0]
                for tc in t.iter("testcase") if tc.find("failure") is not None or tc.find("error") is not None})
files = [f for f in files if (scratch / f).is_file()]
t0 = time.time()
SKIP_LIVE = os.environ.get("BENCH_SKIP_LIVE") == "1"
res = gs.run_pytest(scratch, files[:0] if SKIP_LIVE else files, timeout=1800, sbfl=True)
live = {}
_orig_sbfl_ranked = gs.sbfl_ranked
for mode in MODES:
    os.environ["ETHER_SBFL_RANK"] = mode if mode in ("ochiai", "hub") else "b5"
    gs.sbfl_ranked = (lambda root, nid, spectra, text, _m=mode: ranked(_m, spectra or {}, nid, text or ""))
    vias, targets, reasons = {}, {}, {}
    for nid, text in res["fail"].items():
        goal, reason = gs.classify_failure(scratch, nid, text, res.get("spectra"))
        if goal is not None and not gs.fits_reply(scratch, goal):
            goal, reason = None, "too_large"
        reasons[reason] = reasons.get(reason, 0) + 1
        if goal is None:
            continue
        vias[goal.get("via")] = vias.get(goal.get("via"), 0) + 1
        if goal.get("via") == "sbfl":
            k = goal["file"] + "::" + goal["symbol"]
            targets[k] = targets.get(k, 0) + 1
    n = max(1, sum(targets.values()))
    live[mode] = {"failing": len(res["fail"]), "goals": sum(vias.values()), "vias": vias, "reasons": reasons,
                  "sbfl_goals": sum(targets.values()), "distinct_sbfl_targets": len(targets),
                  "largest_target_share": round(max(targets.values() or [0]) / n, 3),
                  "registry_execute_share": round(targets.get("core/registry.py::GemRegistry.execute", 0) / n, 3),
                  "sbfl_targets": dict(sorted(targets.items(), key=lambda kv: -kv[1]))}
os.environ.pop("ETHER_SBFL_RANK", None)
gs.sbfl_ranked = _orig_sbfl_ranked
doc["live"] = live
doc["live_secs"] = round(time.time() - t0, 1)
print(json.dumps({m: {k: v for k, v in r.items() if k != "sbfl_targets"} for m, r in live.items()}, indent=1), flush=True)


# ---------------- B. mutants
class Mut(ast.NodeTransformer):
    """Mutate the k-th eligible site (k=0: batch-4 operator, same order)."""
    FLIP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE,
            ast.LtE: ast.Gt, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}

    def __init__(self, k=0):
        self.done = None
        self.k = k
        self.seen = 0

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
    return node if isinstance(node, ast.FunctionDef) else None


def mutate(rel, qual, k=0):
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
    seg = ast.unparse(node)
    indent = " " * node.col_offset
    seg = "".join(indent + l + "\n" for l in seg.splitlines())
    p.write_text("".join(lines[:start - 1]) + seg + "".join(lines[node.end_lineno:]), encoding="utf-8")
    return m.done, text


def size_ok(rel, qual, hi=60):
    try:
        node = find(ast.parse((scratch / rel).read_text(encoding="utf-8")), qual)
    except Exception:
        return False
    return node is not None and 3 <= (node.end_lineno - node.lineno) <= hi


ALL_TESTS = False


def run_set(name, cands, n_want):
    base_status, rows, tried = {}, [], 0
    for cand in cands:
        rel, qual, tfs = cand[:3]
        k = cand[3] if len(cand) > 3 else 0
        if len([r for r in rows if r["sbfl_tests"]]) >= n_want or tried >= n_want * 4:
            break
        tried += 1
        key = tuple(tfs)
        if key not in base_status:
            base_status[key] = gs.run_pytest(scratch, list(tfs), timeout=240)["status"]
        op, original = mutate(rel, qual, k)
        if op is None:
            continue
        try:
            r = gs.run_pytest(scratch, list(tfs), timeout=240, sbfl=True)
        finally:
            (scratch / rel).write_text(original, encoding="utf-8")
        newly = [n for n, st in r["status"].items() if st == "fail" and base_status[key].get(n) == "pass"]
        sbfl_tests = [n for n in newly if not gs._repo_frames(scratch, r["fail"].get(n, ""))]
        if ALL_TESTS:
            sbfl_tests = newly  # spectrum ranking forced for every newly failing test (frames ignored)
        per = []
        for nid in sbfl_tests:
            text = r["fail"].get(nid, "")
            out = {}
            for mode in MODES:
                keys = [(rl, q) for s, o, rl, q in ranked(mode, r.get("spectra"), nid, text)
                        if s >= gs.SBFL_MIN and not protected(rl)]
                out[mode] = keys.index((rel, qual)) + 1 if (rel, qual) in keys else None
            per.append(out)
        rows.append({"target": f"{rel}::{qual}", "op": op, "k": k, "files": list(tfs), "newly_failing": len(newly),
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

    out = {"tried": tried, "with_sbfl_tests": sum(1 for r in rows if r["sbfl_tests"]),
           **{m: agg(m) for m in MODES}, "rows": rows}
    print(name, json.dumps({k: v for k, v in out.items() if k != "rows"}), flush=True)
    return out


# F: batch-4 candidate set (top-level functions the tests import), same seed
test_files = sorted(p.relative_to(scratch).as_posix() for p in (scratch / "tests").glob("test_*.py"))
imports = {}
for tf in test_files:
    text = (scratch / tf).read_text(encoding="utf-8", errors="ignore")
    for mod, names in re.findall(r"^from ((?:core|scripts)[\w.]*) import ([\w, ()]+)", text, re.M):
        for n in re.findall(r"\w+", names):
            imports.setdefault((mod.replace(".", "/") + ".py", n), set()).add(tf)
cands = []
for (rel, name), tfs in imports.items():
    if not (scratch / rel).is_file() or protected(rel) or rel.startswith("core/agent/fault_loc"):
        continue
    if size_ok(rel, name):
        cands.append((rel, name, sorted(tfs)[:3]))
cands.sort()
random.Random(4).shuffle(cands)
doc["mutants_F"] = run_set("F", cands, n_func) if n_func else {}

# D: methods behind dispatchers, test files from the full-suite spectrum
mcands = []
if full and full.is_file() and n_meth:
    spec = json.loads(full.read_text(encoding="utf-8")).get("tests") or {}
    who = {}
    for nid, row in spec.items():
        if row.get("outcome") != "passed":
            continue
        for rel, qual in row.get("calls") or []:
            if "." in qual:
                who.setdefault((rel, qual), set()).add(nid.split("::")[0])
    from core.agent.fault_loc import dispatchers

    reached = set()
    for callees in dispatchers({"tests": spec}).values():
        reached |= {tuple(c) for c in callees if not c[0].startswith("~")}
    for (rel, qual), tfs in who.items():
        if protected(rel) or qual.count(".") != 1 or rel.startswith("core/agent/"):
            continue
        if (rel, qual) in reached and (scratch / rel).is_file() and size_ok(rel, qual, hi=200):
            for k in range(4):
                mcands.append((rel, qual, sorted(tfs, key=lambda f: (scratch / f).stat().st_size)[:3], k))
    mcands.sort()
    random.Random(5).shuffle(mcands)
    # D = handler methods a dispatcher reached in the full run (ground truth for gap 1). Every
    # newly failing test counts: the ranker is forced even when a frame would have localised it.
    ALL_TESTS = True
    doc["mutants_D"] = run_set("D", mcands, n_meth)
    doc["mutants_D"]["candidates"] = len(mcands)
    doc["mutants_D"]["note"] = "all newly failing tests ranked (frames ignored)"
    ALL_TESTS = False

outp.parent.mkdir(parents=True, exist_ok=True)
outp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
shutil.rmtree(scratch.parent, ignore_errors=True)
