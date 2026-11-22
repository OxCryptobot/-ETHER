"""Batch 5 (2026-11-21): dispatcher-aware + evidence fault localisation, transactional
multi-target / new-file edits (ETHER_MULTI_EDIT), publish noise, host self-check, post-pull
smoke + local rollback pin. Every edit still goes through the honest gate."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETHER_SOTA_LEGACY", "0")
    monkeypatch.setenv("ETHER_GOAL_SOURCE", "1")
    monkeypatch.setenv("ETHER_GOAL_SCAN", "1")
    monkeypatch.setenv("ETHER_SOTA_EXPLORE", "0")
    for k in ("ETHER_EDIT_CONSTANTS", "ETHER_SBFL", "ETHER_REFACTOR", "ETHER_MULTI_EDIT", "ETHER_SBFL_RANK",
              "ETHER_PULL_ROLLBACK", "ETHER_MODEL_CTX", "ETHER_SMOKE"):
        monkeypatch.delenv(k, raising=False)


def _repo(tmp_path: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- 1+2: localisation

def _spectra(fail_edges, pass_rows):
    tests = {"t::f": {"outcome": "failed", "calls": [list(c) for c in fail_edges["calls"]],
                      "edges": [[list(a), list(b)] for a, b in fail_edges["edges"]]}}
    for i, row in enumerate(pass_rows):
        tests[f"t::p{i}"] = {"outcome": "passed", "calls": [list(c) for c in row["calls"]],
                             "edges": [[list(a), list(b)] for a, b in row.get("edges", [])]}
    return {"tests": tests}


REG = ("core/registry.py", "GemRegistry.execute")
RUN = ("core/pipeline.py", "Pipeline._run_audit")
H1 = ("gems/a/gem.py", "AGem.execute")
H2 = ("gems/b/gem.py", "BGem.execute")
H3 = ("gems/c/gem.py", "CGem.execute")


def test_dispatcher_is_detected_by_polymorphic_fanout() -> None:
    from core.agent.fault_loc import dispatchers

    sp = _spectra({"calls": [RUN, REG, H1], "edges": [(RUN, REG), (REG, H1)]},
                  [{"calls": [RUN, REG, H2], "edges": [(RUN, REG), (REG, H2)]},
                   {"calls": [RUN, REG, H3], "edges": [(RUN, REG), (REG, H3)]}])
    d = dispatchers(sp)
    assert REG in d and RUN not in d


def test_rank5_points_at_the_handler_the_failing_test_reached() -> None:
    """Batch 4 ranked the registry first for 35% of SBFL goals; the fault is in the handler."""
    from core.agent.fault_loc import rank, rank5

    # the failing test reached AGem; passing tests reached the other gems, and some reached AGem too
    sp = _spectra({"calls": [RUN, REG, H1], "edges": [(RUN, REG), (REG, H1)]},
                  [{"calls": [RUN, REG, H2], "edges": [(RUN, REG), (REG, H2)]},
                   {"calls": [RUN, REG, H3], "edges": [(RUN, REG), (REG, H3)]},
                   {"calls": [REG, H1], "edges": [(REG, H1)]}])
    assert rank(sp, "t::f")[0][3] != "AGem.execute" or True  # batch 4 may or may not
    top = rank5(sp, "t::f")[0]
    assert top[3] == "AGem.execute"
    assert [r for r in rank5(sp, "t::f") if r[3] == "GemRegistry.execute"][0][0] < top[0]


def test_rank5_moves_to_the_repo_caller_when_the_handler_is_a_test_stub() -> None:
    from core.agent.fault_loc import rank5

    stub = ("~tests/test_x.py", "ScriptedGem.execute")
    stub2 = ("~tests/test_x.py", "OtherGem.execute")
    sp = _spectra({"calls": [RUN, REG], "edges": [(RUN, REG), (REG, stub)]},
                  [{"calls": [REG], "edges": [(REG, stub2)]}, {"calls": [REG], "edges": [(REG, stub)]}])
    ranked = rank5(sp, "t::f")
    assert ranked[0][3] == "Pipeline._run_audit"


def test_evidence_reads_pytest_where_names_literals_and_frames() -> None:
    from core.agent.fault_loc import evidence

    text = ("tests/test_a.py:12: in test_x\n    assert loop_runner_enabled() is False\n"
            "E   assert True is False\n E    +  where True = <function loop_runner_enabled at 0x7f>()\n"
            "E   AssertionError: assert ['host execution: sandbox not isolated'] == []\n"
            "core/x.py:40: in helper\n")
    ev = evidence(text)
    assert "loop_runner_enabled" in ev["names"]
    assert "host execution: sandbox not isolated" in ev["literals"]
    assert ("core/x.py", 40) in ev["frames"]


def test_rank5_literal_evidence_breaks_a_tie(tmp_path: Path) -> None:
    from core.agent.fault_loc import rank5

    root = _repo(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/posture.py": ("def notes(cfg):\n    out = []\n    if not cfg.get('iso'):\n"
                           "        out.append('host execution: sandbox not isolated')\n    return out\n\n\n"
                           "def other(cfg):\n    return dict(cfg)\n"),
    })
    a, b = ("pkg/posture.py", "notes"), ("pkg/posture.py", "other")
    sp = _spectra({"calls": [b, a], "edges": []}, [{"calls": [], "edges": []}])
    text = "E   AssertionError: assert ['host execution: sandbox not isolated'] == []\n"
    plain = rank5(sp, "t::f")
    assert plain[0][0] == [r for r in plain if r[3] == "notes"][0][0]  # tie without evidence
    with_ev = rank5(sp, "t::f", root=str(root), text=text)
    assert with_ev[0][3] == "notes" and with_ev[0][0] > with_ev[1][0]


DISPATCH_FILES = {
    "pkg/__init__.py": "",
    "pkg/registry.py": ("class Registry:\n    def __init__(self):\n        self.h = {}\n\n"
                        "    def register(self, name, h):\n        self.h[name] = h\n\n"
                        "    def execute(self, name, x):\n        return self.h[name].execute(x)\n"),
    "pkg/handlers.py": ("class Double:\n    def execute(self, x):\n        return x * 2\n\n\n"
                        "class Square:\n    def execute(self, x):\n        return x * x + 1\n\n\n"
                        "class Neg:\n    def execute(self, x):\n        return -x\n\n\n"
                        "def build():\n    from pkg.registry import Registry\n    r = Registry()\n"
                        "    r.register('d', Double())\n    r.register('s', Square())\n    r.register('n', Neg())\n"
                        "    return r\n"),
    "tests/test_disp.py": ("from pkg.handlers import build\n\n\n"
                           "def test_double():\n    assert build().execute('d', 3) == 6\n\n\n"
                           "def test_neg():\n    assert build().execute('n', 3) == -3\n\n\n"
                           "def test_double_again():\n    assert build().execute('d', 4) == 8\n\n\n"
                           "def test_square():\n    assert build().execute('s', 3) == 9\n"),
}


def test_live_plugin_records_edges_and_goal_targets_the_handler(tmp_path: Path, monkeypatch) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path, DISPATCH_FILES)
    res = gs.run_pytest(root, ["tests/test_disp.py"], sbfl=True)
    nid = "tests/test_disp.py::test_square"
    assert res["status"][nid] == "fail"
    edges = res["spectra"]["tests"][nid]["edges"]
    assert [["pkg/registry.py", "Registry.execute"], ["pkg/handlers.py", "Square.execute"]] in edges
    monkeypatch.setenv("ETHER_SBFL_RANK", "b5")
    top = gs.sbfl_ranked(root, nid, res["spectra"], res["fail"][nid])[0]
    assert (top[2], top[3]) == ("pkg/handlers.py", "Square.execute")


def test_package_init_module_is_targetable(tmp_path: Path) -> None:
    """`from core.loop import loop_runner_enabled` was dropped: core/loop.py does not exist."""
    from core.agent import goal_source as gs

    root = _repo(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/loop/__init__.py": "import os\n\n\ndef enabled():\n    return os.getenv('X_LOOP', '1') == '1'\n",
        "tests/test_loop.py": "from pkg.loop import enabled\n\n\ndef test_off():\n    assert enabled() is False\n",
    })
    assert gs.mod_rel(root, "pkg.loop") == "pkg/loop/__init__.py"
    gs.scan(root, n_files=5)
    goal = gs.next_real(root)
    assert goal and goal["file"] == "pkg/loop/__init__.py" and goal["symbol"] == "enabled"


# ---------------------------------------------------------------- 3: multi-target edits

def test_filetx_reverts_every_file_and_removes_a_new_one(tmp_path: Path) -> None:
    from core.kernel.edit_tx import FileTx

    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    tx = FileTx(tmp_path, ["a.py", "new/pkg/b.py"]).begin()
    (tmp_path / "a.py").write_text("A = 2\n", encoding="utf-8")
    (tmp_path / "new" / "pkg").mkdir(parents=True)
    (tmp_path / "new" / "pkg" / "b.py").write_text("B = 1\n", encoding="utf-8")
    assert sorted(tx.changed()) == ["a.py", "new/pkg/b.py"]
    tx.revert()
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "A = 1\n"
    assert not (tmp_path / "new").exists()


TWO_FILES = {
    "pkg/__init__.py": "",
    "pkg/store.py": "def get(d, key):\n    return d[key]\n",
    "pkg/api.py": "from pkg.store import get\n\n\ndef fetch(d):\n    return get(d, 'name')\n",
    "tests/test_two.py": (
        "def test_fetch_default():\n"
        "    from pkg.api import fetch\n"
        "    from pkg.store import get\n"
        "    assert get({}, 'name', default=7) == 7\n"
        "    assert fetch({}) == 0\n\n\n"
        "def test_get_existing():\n"
        "    from pkg.store import get\n"
        "    assert get({'name': 3}, 'name') == 3\n\n\n"
        "def test_fetch_existing():\n"
        "    from pkg.api import fetch\n"
        "    assert fetch({'name': 5}) == 5\n"
    ),
}
GOOD_STORE = "def get(d, key, default=None):\n    return d.get(key, default)\n"
GOOD_API = "def fetch(d):\n    return get(d, 'name', default=0)\n"
TWO_ORACLE = f"# file: pkg/api.py\n{GOOD_API}\n# file: pkg/store.py\n{GOOD_STORE}"
TWO_CHEAT_CONST = ("# file: pkg/api.py\ndef fetch(d):\n    return 0\n\n"
                   "# file: pkg/store.py\ndef get(d, key, default=None):\n    return 7\n")
TWO_CHEAT_TEST = f"# file: pkg/api.py\n{GOOD_API}\n# file: tests/test_two.py\ndef test_fetch_default():\n    pass\n"
TWO_HALF = f"# file: pkg/store.py\n{GOOD_STORE}"
SINGLE_WRONG = "def fetch(d):\n    return get(d, 'name') if d else 0\n"


def _ask_for(multi_reply: str):
    seen = []

    def ask(prompt: str, n: int = 240) -> str:
        seen.append(prompt)
        return multi_reply if "# file: <path>" in prompt else SINGLE_WRONG
    ask.seen = seen  # type: ignore[attr-defined]
    return ask


def _two_repo(tmp_path: Path) -> Path:
    from core.agent import goal_source as gs

    root = _repo(tmp_path, TWO_FILES)
    gs.scan(root, n_files=5)
    return root


def _reset_tries(root: Path) -> None:
    from core.agent import goal_source as gs

    data = gs.load_index(root)
    data["tries"] = {"fix_test_fetch_default": 1}
    gs.save_index(root, data)


def test_multi_off_keeps_single_target_goals(tmp_path: Path) -> None:
    from core.agent import goal_source as gs

    root = _two_repo(tmp_path)
    goal = gs.next_real(root)
    assert goal["file"] == "pkg/api.py" and goal["symbol"] == "fetch"
    assert "alt_targets" not in goal and "targets" not in goal


def test_multi_goal_gets_the_second_place_from_the_test(tmp_path: Path, monkeypatch) -> None:
    from core.agent import goal_source as gs

    monkeypatch.setenv("ETHER_MULTI_EDIT", "1")
    root = _two_repo(tmp_path)
    goal = gs.next_real(root)
    assert goal["alt_targets"] == [{"file": "pkg/store.py", "symbol": "get", "kind": "function"}]


@pytest.mark.parametrize("ctx", [2048, 4096, 8192])
def test_multi_prompt_fits_the_context_and_holds_no_answer(tmp_path: Path, monkeypatch, ctx: int) -> None:
    from core.agent import goal_source as gs
    from core.agent import multi_edit
    from core.agent.goal_quality import check
    from core.kernel.context_budget import context_char_budget

    monkeypatch.setenv("ETHER_MULTI_EDIT", "1")
    monkeypatch.setenv("ETHER_MODEL_CTX", str(ctx))
    root = _two_repo(tmp_path)
    goal = gs.next_real(root)
    places = multi_edit.targets_of(goal, tries=1)
    prompt, kept = multi_edit.build_prompt(root, goal, places)
    assert len(kept) == 2 and 0 < len(prompt) <= context_char_budget()
    assert "default=0" not in prompt and "d.get(key, default)" not in prompt
    cur = "\n".join((root / t["file"]).read_text(encoding="utf-8") for t in kept)
    assert check(goal, prompt, cur)["ok"]


def test_mock_replay_two_file_fix_kept_after_single_try_fails(tmp_path: Path, monkeypatch) -> None:
    from core.agent import goal_source as gs
    from core.agent import sota

    monkeypatch.setenv("ETHER_MULTI_EDIT", "1")
    root = _two_repo(tmp_path)
    ask = _ask_for(TWO_ORACLE)
    row = sota.run(root, ask)  # single place first: cannot pass
    assert row["kept_n"] == 0
    assert (root / "pkg" / "api.py").read_text(encoding="utf-8") == TWO_FILES["pkg/api.py"]
    row = sota.run(root, ask)  # escalates to both places in one transaction
    assert row["kept_n"] == 1 and row.get("multi") == 2 and row.get("regressions") == 0
    assert "default=0" in (root / "pkg" / "api.py").read_text(encoding="utf-8")
    assert "d.get(key, default)" in (root / "pkg" / "store.py").read_text(encoding="utf-8")
    assert gs.run_pytest(root, ["tests/test_two.py"])["ok"]


@pytest.mark.parametrize("reply,note", [
    (TWO_CHEAT_CONST, "regression"),      # passes the target, breaks two passing tests
    (TWO_CHEAT_TEST, "no edit: path not in the goal: tests/test_two.py"),
    (TWO_HALF, "tests failed"),           # one half only
])
def test_mock_replay_multi_cheats_are_reverted(tmp_path: Path, monkeypatch, reply: str, note: str) -> None:
    from core.agent import sota

    monkeypatch.setenv("ETHER_MULTI_EDIT", "1")
    root = _two_repo(tmp_path)
    _reset_tries(root)
    row = sota.run(root, _ask_for(reply))
    assert row["kept_n"] == 0 and row["note"] == note
    for rel in ("pkg/api.py", "pkg/store.py", "tests/test_two.py"):
        assert (root / rel).read_text(encoding="utf-8") == TWO_FILES[rel]


def test_protected_path_is_refused_even_if_named(tmp_path: Path) -> None:
    from core.agent import multi_edit

    res = multi_edit.apply(tmp_path, [{"target": {"file": "core/agent/sota.py", "symbol": "x", "kind": "function"},
                                       "function": "def x():\n    return 1\n"}])
    assert res["ok"] is False and "protected" in res["reason"]


NEW_MOD = {
    "pkg/__init__.py": "",
    "pkg/old.py": "def one():\n    return 1\n",
    "tests/test_new.py": ("def test_double():\n    from pkg.newmod import double\n    assert double(4) == 8\n\n\n"
                          "def test_one():\n    from pkg.old import one\n    assert one() == 1\n"),
}


def test_new_module_goal_creates_a_small_file_and_reverts_a_wrong_one(tmp_path: Path, monkeypatch) -> None:
    from core.agent import goal_source as gs
    from core.agent import sota

    root = _repo(tmp_path, NEW_MOD)
    gs.scan(root, n_files=5)
    assert gs.load_index(root)["dropped"]  # flag off: not goalable
    monkeypatch.setenv("ETHER_MULTI_EDIT", "1")
    (root / "artifacts" / "goal_index.json").unlink()
    gs.scan(root, n_files=5)
    goal = gs.next_real(root)
    assert goal["via"] == "new_module" and goal["targets"][0]["kind"] == "new_file"
    assert goal["targets"][0]["names"] == ["double"]
    row = sota.run(root, lambda p, n=240: "# file: pkg/newmod.py\ndef double(x):\n    return x + 2\n")
    assert row["kept_n"] == 0 and not (root / "pkg" / "newmod.py").exists()
    data = gs.load_index(root)
    data["tries"] = {}
    gs.save_index(root, data)
    row = sota.run(root, lambda p, n=240: "# file: pkg/newmod.py\ndef double(x):\n    return 2 * x\n")
    assert row["kept_n"] == 1 and (root / "pkg" / "newmod.py").is_file()


def test_listed_sites_become_places_up_to_three(tmp_path: Path) -> None:
    from core.agent import multi_edit

    root = _repo(tmp_path, {
        "core/__init__.py": "",
        "core/a.py": "def f():\n    import gems.x\n    return 1\n",
        "core/b.py": "def g():\n    import gems.y\n    return 2\n",
        "core/c.py": "def h():\n    import gems.z\n    return 3\n",
        "core/d.py": "def k():\n    import gems.w\n    return 4\n",
    })
    two = "E       core/a.py:2 imports gems.x\nE       core/b.py:2 imports gems.y\n"
    t, why = multi_edit.site_targets(root, two)
    assert why == "" and [x["symbol"] for x in t] == ["f", "g"]
    four = two + "E       core/c.py:2 imports gems.z\nE       core/d.py:2 imports gems.w\n"
    assert multi_edit.site_targets(root, four) == ([], "too_many_sites")
    frame = "core/a.py:2: in f\n"
    assert multi_edit.site_targets(root, frame)[1] == "no_sites"  # traceback frames are not sites


def test_syntax_error_file_becomes_a_whole_file_place(tmp_path: Path) -> None:
    from core.agent import multi_edit

    root = _repo(tmp_path, {"scripts/snip.py": "    def broken(:\n        pass\n"})
    text = ('E     File "scripts/snip.py", line 1\nE       def broken(:\nE       ^\n'
            "E   IndentationError: unexpected indent\n")
    assert multi_edit.syntax_file_target(root, text) == {"file": "scripts/snip.py", "symbol": "", "kind": "file"}


# ---------------------------------------------------------------- 4: publish noise

class _Proc:
    def __init__(self, rc=0, out=""):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def test_urgent_only_when_origin_would_really_change(tmp_path: Path) -> None:
    """Batch 2 bypassed the throttle whenever a listed code path was dirty."""
    from scripts.origin_publish import publishable_code

    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "a.py").write_text("x\n", encoding="utf-8")
    blobs = {"origin/main:core/a.py": "B1", "MB:core/a.py": "B1"}

    def runner(local_blob):
        def run(argv):
            if "status" in argv:
                return _Proc(0, " M core/a.py\n")
            if "merge-base" in argv:
                return _Proc(0, "MB\n")
            if "rev-parse" in argv:
                ref = argv[-1]
                return _Proc(0, blobs[ref] + "\n") if ref in blobs else _Proc(1, "")
            if "hash-object" in argv:
                return _Proc(0, local_blob + "\n")
            return _Proc(0, "")
        return run

    assert publishable_code(tmp_path, "git", runner("B1"), ["core/a.py"]) == []   # dirty but same as origin
    assert publishable_code(tmp_path, "git", runner("B2"), ["core/a.py"]) == ["core/a.py"]
    blobs["origin/main:core/a.py"] = "B3"  # upstream changed it: copy is skipped, so not urgent
    assert publishable_code(tmp_path, "git", runner("B2"), ["core/a.py"]) == []


def test_idle_cadence_ignores_jobs_no_host_drainer_runs(tmp_path: Path, monkeypatch) -> None:
    from scripts import host_supervisor as hs

    pend = tmp_path / "artifacts" / "jobs" / "pending"
    pend.mkdir(parents=True)
    (pend / "medic_hb_1.json").write_text(json.dumps({"id": "m", "steps": [{"argv": ["python", "x.py"]}]}),
                                          encoding="utf-8")
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    assert hs.drainable_count(tmp_path) == 0
    assert hs.idle_s() == 60.0
    (pend / "edit_1.json").write_text(json.dumps({"id": "e", "steps": [{"argv": ["python", "-m", "scripts.live_edit_tx"]}]}),
                                      encoding="utf-8")
    assert hs.drainable_count(tmp_path) == 1


def test_publish_sim_day_is_bounded() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("publish_sim", "docs/results/batch5/publish_sim.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    old = mod.simulate("old")
    new_dry = mod.simulate("b5_dry")
    new_busy = mod.simulate("b5_busy")
    assert old["commits_per_hour"] > 150
    assert new_dry["commits_per_hour"] <= 4.5
    assert new_busy["commits_per_hour"] <= 13
    assert mod.simulate("b2_dirty")["commits_per_hour"] > mod.simulate("b5_dirty")["commits_per_hour"]


# ---------------------------------------------------------------- 5: self-check, smoke, rollback

def test_selfcheck_names_the_broken_import(tmp_path: Path) -> None:
    from scripts.host_selfcheck import check_imports, compile_host

    root = _repo(tmp_path, {
        "zzb5core/__init__.py": "",
        "zzb5core/plan.py": "def other():\n    return 0\n",
        "zzb5scripts/__init__.py": "",
        "zzb5scripts/main.py": "def tick():\n    from zzb5core.plan import heartbeat_plan\n    return heartbeat_plan()\n",
    })
    import sys

    try:
        out = check_imports(root, ("zzb5scripts/main.py",), pkgs=("zzb5core",))
        assert out["ok"] is False
        assert out["broken"][0].startswith("zzb5scripts/main.py:2 zzb5core.plan.heartbeat_plan: ImportError")
        assert compile_host(root, ("zzb5scripts/main.py",))["ok"] is True
        (root / "zzb5core" / "plan.py").write_text("def heartbeat_plan():\n    return 1\n", encoding="utf-8")
        for m in ("zzb5core", "zzb5core.plan"):
            sys.modules.pop(m, None)
        assert check_imports(root, ("zzb5scripts/main.py",), pkgs=("zzb5core",))["ok"] is True
    finally:
        for m in ("zzb5core", "zzb5core.plan"):
            sys.modules.pop(m, None)
        if str(root) in sys.path:
            sys.path.remove(str(root))


def test_selfcheck_passes_on_this_tree() -> None:
    from scripts.host_selfcheck import smoke

    out = smoke(Path("."))
    assert out["ok"] is True, out


def test_host_main_writes_a_broken_selfcheck_loudly(tmp_path: Path, monkeypatch) -> None:
    from scripts import host_main, host_selfcheck

    monkeypatch.setattr(host_selfcheck, "check_imports",
                        lambda root=None: {"ok": False, "broken": ["scripts/host_main.py:206 core.kernel.plan.heartbeat_plan: ImportError: x"],
                                           "n_broken": 1})
    row: dict = {}
    host_main._selfcheck(tmp_path, row)
    assert row["health"] == "degraded" and "heartbeat_plan" in row["selfcheck_error"]
    on_disk = json.loads((tmp_path / "artifacts" / "host_main.json").read_text(encoding="utf-8"))
    assert "heartbeat_plan" in on_disk["selfcheck_error"]


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env, check=True).stdout.strip()


def _host_and_origin(tmp_path: Path):
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    up = tmp_path / "up"
    _git(tmp_path, "clone", "-q", str(origin), str(up))
    (up / "code.py").write_text("GOOD = 1\n", encoding="utf-8")
    (up / "artifacts").mkdir()
    (up / "artifacts" / "beat.json").write_text("{}\n", encoding="utf-8")
    _git(up, "add", "-A")
    _git(up, "commit", "-q", "-m", "good")
    _git(up, "push", "-q", "origin", "HEAD:main")
    host = tmp_path / "host"
    _git(tmp_path, "clone", "-q", str(origin), str(host))
    return origin, up, host


def _push(up: Path, rel: str, text: str, msg: str) -> str:
    (up / rel).write_text(text, encoding="utf-8")
    _git(up, "add", "-A")
    _git(up, "commit", "-q", "-m", msg)
    _git(up, "push", "-q", "origin", "HEAD:main")
    return _git(up, "rev-parse", "HEAD")


def _smoke(base: Path) -> dict:
    ok = "BROKEN" not in (base / "code.py").read_text(encoding="utf-8")
    return {"ok": ok, "imports": {"broken": [] if ok else ["code.py:1 BROKEN"]}}


def _sup(host: Path):
    from scripts.host_supervisor import Supervisor

    return Supervisor(host, run=lambda b: {"ok": True}, ollama=lambda: {"ok": True},
                      changed=lambda b, x, y: False, sleep=lambda s: None, idle=lambda: 1.0, smoke=_smoke)


def test_post_pull_smoke_without_rollback_flag_reports_and_runs_on(tmp_path: Path) -> None:
    from scripts import host_pin

    _origin, up, host = _host_and_origin(tmp_path)
    good = _git(host, "rev-parse", "HEAD")
    bad = _push(up, "code.py", "BROKEN = 1\n", "bad")
    row = _sup(host).once()
    assert row["pull"]["smoke"]["ok"] is False
    assert "off" in row["pull"]["rollback"]["note"]
    assert _git(host, "rev-parse", "HEAD") == bad and not host_pin.pinned(host)
    assert good != bad


def test_post_pull_smoke_rolls_back_locally_and_pins(tmp_path: Path, monkeypatch) -> None:
    from scripts import host_pin

    monkeypatch.setenv("ETHER_PULL_ROLLBACK", "1")
    _origin, up, host = _host_and_origin(tmp_path)
    good = _git(host, "rev-parse", "HEAD")
    sup = _sup(host)
    bad = _push(up, "code.py", "BROKEN = 1\n", "bad")
    row = sup.once()
    assert row["pull"]["rollback"]["ok"] is True
    assert _git(host, "rev-parse", "HEAD") == good
    assert host_pin.pin(host)["bad"] == bad and "BROKEN" in host_pin.pin(host)["why"][0]
    # artifact-only commits on top of the bad tip: still pinned, not pulled again
    _push(up, "artifacts/beat.json", '{"n": 1}\n', "1650 host_main")
    row = sup.once()
    assert row["pull"]["note"] == "pinned" and _git(host, "rev-parse", "HEAD") == good
    # a real upstream fix clears the pin, passes the smoke and becomes the last good commit
    fixed = _push(up, "code.py", "GOOD = 2\n", "fix")
    row = sup.once()
    assert row["pull"]["smoke"]["ok"] is True and not host_pin.pinned(host)
    assert _git(host, "rev-parse", "HEAD") == fixed == host_pin.last_good(host)
    assert _git(origin_head := up, "rev-parse", "HEAD") == fixed  # nothing was pushed from the host
    del origin_head


def test_rollback_never_discards_local_changes(tmp_path: Path, monkeypatch) -> None:
    from scripts import host_pin

    monkeypatch.setenv("ETHER_PULL_ROLLBACK", "1")
    _origin, up, host = _host_and_origin(tmp_path)
    sup = _sup(host)
    _push(up, "code.py", "BROKEN = 1\n", "bad")
    sup.pull(host)  # fast-forward first (no smoke here), then dirty the bad file locally
    (host / "code.py").write_text("BROKEN = 1\nlocal = 1\n", encoding="utf-8")
    run = lambda argv: subprocess.run([argv[0], "-C", str(host), *argv[1:]], capture_output=True, text=True)  # noqa: E731
    good = _git(host, "rev-parse", "HEAD~1")
    res = host_pin.rollback(host, run, "git", good, _git(host, "rev-parse", "HEAD"), {"ok": False})
    assert res["ok"] is False  # --keep refuses; never --hard
    assert "local = 1" in (host / "code.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- 6: tick-path gaps

def test_ollama_call_sends_a_fixed_context_window(monkeypatch) -> None:
    """Prompts are budgeted for ETHER_MODEL_CTX; Ollama must not silently fall back to 2048."""
    import io
    import urllib.request

    from scripts import live_edit_tx

    sent = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        sent["body"] = json.loads(req.data.decode())
        sent["timeout"] = timeout
        return _Resp(json.dumps({"message": {"content": "ok"}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("scripts.live_generate_probe.pick_model", lambda: "qwen3.5:4b")
    assert live_edit_tx._ask("hi", n=768, edit=True) == "ok"
    assert sent["body"]["options"]["num_ctx"] == 4096 and sent["body"]["options"]["num_predict"] == 768
    assert sent["timeout"] >= 240
    monkeypatch.setenv("ETHER_NUM_CTX", "8192")
    live_edit_tx._ask("hi", n=240)
    assert sent["body"]["options"]["num_ctx"] == 8192


def test_host_main_errors_carry_the_message() -> None:
    src = Path("scripts/host_main.py").read_text(encoding="utf-8")
    assert '_error"] = type(exc).__name__' not in src
    assert "_write_row(root, row)\n        try:\n            from scripts.origin_publish import publish" in src
