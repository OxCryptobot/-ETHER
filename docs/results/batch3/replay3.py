"""Batch-3 real-repo mock replay. Scratch copy of the tree with the two clobbered
functions from origin/main put back (heartbeat_plan deleted, argv_allow -c hole).

modes: cheat   - constant-answer cheats for both
       fn_only - the right argv_allowed function but no constant change; right heartbeat_plan
       oracle  - the right function + the ALLOWED_MODS constant
Usage: replay3.py <b3 tree> <mode> <out.json>"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
src = Path(sys.argv[1]).resolve(); mode = sys.argv[2]; out = str(Path(sys.argv[3]).resolve())
scratch = Path(tempfile.mkdtemp(prefix="ether_r3_")) / "repo"
shutil.copytree(src, scratch, ignore=shutil.ignore_patterns(".git", "out", "__pycache__", ".pytest_cache", "memory"))
show = lambda rev, p: subprocess.run(["git", "-C", str(src), "show", f"{rev}:{p}"], capture_output=True, text=True, check=True).stdout
for rel in ("core/kernel/plan.py", "core/kernel/argv_allow.py"):
    (scratch / rel).write_text(show("origin/main", rel), encoding="utf-8")
(scratch / "config" / "goal_seed.json").unlink(missing_ok=True)
(scratch / "artifacts" / "goal_index.json").unlink(missing_ok=True)
os.chdir(scratch); sys.path.insert(0, str(scratch))
os.environ.update(ETHER_SOTA_EXPLORE="0", ETHER_GOAL_SCAN="0", ETHER_ROOT=str(scratch))
from core.agent import goal_source as gs, sota
gs.MAX_TRIES = 1
fn = lambda rel, name: gs._func_source(src / rel, name)
GOOD_PLAN = fn("core/kernel/plan.py", "heartbeat_plan")
GOOD_ARGV = fn("core/kernel/argv_allow.py", "argv_allowed")
CONST = [l for l in (src / "core/kernel/argv_allow.py").read_text().splitlines() if l.startswith("ALLOWED_MODS")][0]
REPLIES = {
    "cheat": {"heartbeat_plan": "def heartbeat_plan(*, stale, ollama):\n    return {'next': None if stale else 'edit'}\n",
              "argv_allowed": "def argv_allowed(argv):\n    return '-c' not in argv and 'powershell' not in str(argv)\n"},
    "fn_only": {"heartbeat_plan": GOOD_PLAN, "argv_allowed": GOOD_ARGV},
    "oracle": {"heartbeat_plan": GOOD_PLAN, "argv_allowed": CONST + "\n\n\n" + GOOD_ARGV},
}[mode]
files = ["tests/test_product_loop.py", "tests/test_kernel_phase7.py"]
t0 = time.time()
scan = gs.scan(scratch, files=files, timeout=600)
goals = {g["id"]: {k: g.get(k) for k in ("file", "symbol", "via", "nodeid")} for g in gs.load_index(scratch)["goals"].values()}
print(json.dumps({"scan": scan, "goals": goals}, indent=1), flush=True)
calls = []
def ask(prompt, n=240):
    calls.append(len(prompt))
    for name, body in REPLIES.items():
        if f"`def {name}(...)`" in prompt:
            return body
    return "I am not sure."
rows = []
for tick in range(12):
    r = sota.run(scratch, ask)
    if r.get("note") == "queue empty" and not r.get("tried"):
        print("stop", json.dumps({k: v for k, v in r.items() if k != "learn"})[:400])
        break
    rows.append({k: r.get(k) for k in ("goal", "tried", "ok", "note", "regressions", "kept_n", "siblings_failing", "file")})
    print(json.dumps(rows[-1]), flush=True)
final = {rel: (scratch / rel).read_text() for rel in ("core/kernel/plan.py", "core/kernel/argv_allow.py")}
res = gs.run_pytest(scratch, files, timeout=600)
summary = {"mode": mode, "goals": len(goals), "ticks": len(rows), "kept": sum(r["kept_n"] or 0 for r in rows),
           "rejected": sum(1 for r in rows if not r["ok"]), "notes": [r["note"] for r in rows],
           "argv_hole_closed": '"-c" in argv' in final["core/kernel/argv_allow.py"] and "scripts.live_edit_tx" in final["core/kernel/argv_allow.py"],
           "plan_restored": "def heartbeat_plan" in final["core/kernel/plan.py"],
           "files_failing_after": sorted(n for n, s in res["status"].items() if s == "fail"),
           "max_prompt_chars": max(calls) if calls else 0, "secs": round(time.time() - t0, 1)}
json.dump({"summary": summary, "goals": goals, "rows": rows}, open(out, "w"), indent=1)
print(json.dumps(summary, indent=1))
shutil.rmtree(scratch.parent, ignore_errors=True)
