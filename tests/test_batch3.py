"""Batch 3 (2026-11-19): module-level constant edits, SBFL goal coverage, learning
summary, host import paths. Every edit here still goes through the honest gate."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ALLOW_BUGGY = (
    'ALLOWED = frozenset({"pytest", "scripts.anything"})\n'
    "\n\n"
    "def allowed(argv):\n"
    "    if not argv:\n"
    "        return False\n"
    '    if "-c" in argv:\n'
    "        return True\n"
    "    return argv[-1] in ALLOWED\n"
)
ALLOW_TESTS = (
    "from pkg.allow import allowed\n\n\n"
    "def test_allow():\n"
    '    assert allowed(["python", "-m", "pytest"]) is True\n'
    '    assert allowed(["python", "-m", "scripts.anything"]) is False\n'
    '    assert allowed(["python", "-c", "import os"]) is False\n\n\n'
    "def test_empty():\n"
    "    assert allowed([]) is False\n"
)
ALLOW_ORACLE = (
    'ALLOWED = frozenset({"pytest"})\n\n\n'
    "def allowed(argv):\n"
    '    if not argv or "-c" in argv:\n'
    "        return False\n"
    "    return argv[-1] in ALLOWED\n"
)
ALLOW_FN_ONLY = (
    "def allowed(argv):\n"
    '    if not argv or "-c" in argv:\n'
    "        return False\n"
    "    return argv[-1] in ALLOWED\n"
)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETHER_SOTA_LEGACY", "0")
    monkeypatch.setenv("ETHER_GOAL_SOURCE", "1")
    monkeypatch.setenv("ETHER_GOAL_SCAN", "1")
    monkeypatch.setenv("ETHER_SOTA_EXPLORE", "0")
    monkeypatch.delenv("ETHER_EDIT_CONSTANTS", raising=False)
    monkeypatch.delenv("ETHER_SBFL", raising=False)
    monkeypatch.delenv("ETHER_REFACTOR", raising=False)


def _repo(tmp_path: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    return tmp_path


def _allow_repo(tmp_path: Path) -> Path:
    return _repo(tmp_path, {"pkg/__init__.py": "", "pkg/allow.py": ALLOW_BUGGY, "tests/test_allow.py": ALLOW_TESTS})


# ---------------------------------------------------------------- constants (gap 2)

def test_extract_assigns_handles_multiline_and_skips_dunders() -> None:
    from core.agent import goal_source as gs

    reply = "```python\nA = 1\nB = frozenset({\n    'x',\n    'y',\n})\n__all__ = ['f']\nC: int = 3\n\ndef f():\n    return A\n```"
    got = gs.extract_assigns(reply)
    assert sorted(got) == ["A", "B", "C"]
    assert ast.parse(got["B"]).body[0].value.func.id == "frozenset"


def test_function_plus_constant_edit_lands_in_one_write(tmp_path: Path) -> None:
    from core.agent import goal_source as gs

    root = _allow_repo(tmp_path)
    goal = {"file": "pkg/allow.py", "symbol": "allowed"}
    edit = gs.extract_edit(ALLOW_ORACLE, goal)
    assert edit["function"] and list(edit["assigns"]) == ["ALLOWED"]
    out = gs.apply_edit(root, goal, edit)
    assert out["ok"] and out["assigns"] == ["ALLOWED"]
    body = (root / "pkg" / "allow.py").read_text(encoding="utf-8")
    assert body.count("ALLOWED =") == 1 and '{"pytest"}' in body and "scripts.anything" not in body
    compile(body, "allow.py", "exec")


def test_new_constant_only_when_the_function_uses_it(tmp_path: Path) -> None:
    from core.agent import goal_source as gs

    root = _allow_repo(tmp_path)
    goal = {"file": "pkg/allow.py", "symbol": "allowed"}
    used = "BLOCK = ('-c',)\n\ndef allowed(argv):\n    return bool(argv) and not any(a in BLOCK for a in argv)\n"
    out = gs.apply_edit(root, goal, gs.extract_edit(used, goal))
    assert out["ok"]
    body = (root / "pkg" / "allow.py").read_text(encoding="utf-8")
    assert body.index("BLOCK = ") < body.index("def allowed")
    (root / "pkg" / "allow.py").write_text(ALLOW_BUGGY, encoding="utf-8")
    unused = "OTHER = 1\n\ndef allowed(argv):\n    return False\n"
    out = gs.apply_edit(root, goal, gs.extract_edit(unused, goal))
    assert out["ok"] is False and "OTHER" in out["reason"]
    assert (root / "pkg" / "allow.py").read_text(encoding="utf-8") == ALLOW_BUGGY


def test_constant_edits_keep_the_protected_path_guard_and_the_flag(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path, {"core/agent/sota.py": "X = 1\n", "pkg/__init__.py": "", "pkg/allow.py": ALLOW_BUGGY})
    out = gs.apply_edit(root, {"file": "core/agent/sota.py", "symbol": "X", "symbol_kind": "assign"},
                        {"function": "", "assigns": {"X": "X = 2\n"}})
    assert out == {"ok": False, "reason": "protected path"}
    assert (root / "core" / "agent" / "sota.py").read_text(encoding="utf-8") == "X = 1\n"
    monkeypatch.setenv("ETHER_EDIT_CONSTANTS", "0")
    edit = gs.extract_edit(ALLOW_ORACLE, {"file": "pkg/allow.py", "symbol": "allowed"})
    assert edit["assigns"] == {}


def test_module_level_frame_becomes_an_assign_goal_without_the_answer(tmp_path: Path) -> None:
    from core.agent import goal_source as gs
    from core.agent.goal_quality import check

    root = _repo(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/limits.py": "LIMITS = dict(low=1, high=int('x'))\n\n\ndef high():\n    return LIMITS['high']\n",
        "tests/test_limits.py": "def test_high():\n    from pkg.limits import high\n    assert high() == 10\n",
    })
    gs.scan(root, n_files=5)
    goal = gs.next_real(root)
    assert goal is not None and goal["symbol"] == "LIMITS" and goal["symbol_kind"] == "assign"
    prompt = gs.build_prompt(root, goal)
    assert "LIMITS = ..." in prompt and "high=10" not in prompt
    assert check(goal, prompt, (root / "pkg" / "limits.py").read_text(encoding="utf-8"))["ok"]
    assert check(goal, prompt + "\nLIMITS = dict(low=1, high=10)\n",
                 (root / "pkg" / "limits.py").read_text(encoding="utf-8"))["reasons"] == ["spoiler"]


def test_mock_replay_constant_fix_kept_function_only_rejected(tmp_path: Path) -> None:
    """Oracle needs the constant; a function-only reply cannot pass the gate."""
    from core.agent import goal_source as gs
    from core.agent import sota

    root = _allow_repo(tmp_path)
    gs.scan(root, n_files=5)
    goal = gs.next_real(root)
    assert goal and goal["file"] == "pkg/allow.py" and goal["symbol"] == "allowed"
    prompt = gs.build_prompt(root, goal)
    assert 'ALLOWED = frozenset({"pytest", "scripts.anything"})' in prompt  # current constant = context
    assert '"-c" in argv:\n        return False' not in prompt  # not the answer
    row = sota.run(root, lambda prompt, n=240: ALLOW_FN_ONLY)
    assert row["kept_n"] == 0
    assert (root / "pkg" / "allow.py").read_text(encoding="utf-8") == ALLOW_BUGGY
    data = gs.load_index(root)
    data["tries"] = {}
    gs.save_index(root, data)
    row = sota.run(root, lambda prompt, n=240: ALLOW_ORACLE)
    assert row["kept_n"] == 1 and row.get("regressions", 0) == 0
    assert '{"pytest"}' in (root / "pkg" / "allow.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- SBFL coverage (gap 3)

SBFL_SRC = (
    "def parse(text):\n"
    "    return [int(x) for x in text.split(',') if x]\n"
    "\n\n"
    "def total(text):\n"
    "    return sum(parse(text)) + 1\n"
    "\n\n"
    "def count(text):\n"
    "    return len(parse(text))\n"
)
SBFL_TESTS = (
    "import pkg.calc as calc\n\n\n"
    "def test_count():\n"
    "    assert calc.count('1,2') == 2\n\n\n"
    "def test_parse():\n"
    "    assert calc.parse('3') == [3]\n\n\n"
    "def test_total_via_helper():\n"
    "    run = getattr(calc, 'to' + 'tal')\n"
    "    assert run('1,2') == 3\n"
)


def test_sbfl_localises_a_bare_assert_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path, {"pkg/__init__.py": "", "pkg/calc.py": SBFL_SRC, "tests/test_calc.py": SBFL_TESTS})
    monkeypatch.setenv("ETHER_SBFL", "0")
    gs.scan(root, n_files=5)
    data = gs.load_index(root)
    assert data["goals"] == {} and list(data["dropped"].values()) == ["no_repo_target"]
    monkeypatch.setenv("ETHER_SBFL", "1")
    (root / "artifacts" / "goal_index.json").unlink()
    gs.scan(root, n_files=5)
    goal = gs.next_real(root)
    assert goal and goal["via"] == "sbfl" and goal["symbol"] == "total" and goal["file"] == "pkg/calc.py"
    assert goal["suspicion"] >= 1.0  # batch 4: hub-aware rank adds the error-text token bonus
    assert "+ 1" not in gs.build_prompt(root, goal).split("(current)")[0]  # the error/test part has no code


def test_ochiai_ranks_failing_only_functions_first() -> None:
    from core.agent.fault_loc import ochiai

    spectra = {"tests": {
        "t::a": {"outcome": "failed", "calls": [["m.py", "parse"], ["m.py", "total"]]},
        "t::b": {"outcome": "passed", "calls": [["m.py", "parse"], ["m.py", "count"]]},
    }}
    ranked = ochiai(spectra, "t::a")
    assert [r[3] for r in ranked] == ["total", "parse"] and ranked[0][0] == 1.0


def test_classify_failure_reasons(tmp_path: Path) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path, {"pkg/__init__.py": "", "tests/test_x.py": "def test_x():\n    assert 1 == 2\n"})
    assert gs.classify_failure(root, "::tests/test_y.py", "boom") == (None, "collection_error")
    assert gs.classify_failure(root, "tests/test_x.py::test_x", "ConnectionRefusedError: x")[1] == "infra"
    assert gs.classify_failure(root, "tests/test_x.py::test_x", "assert 1 == 2")[1] == "no_repo_target"


def test_sbfl_target_tries_are_shared(tmp_path: Path) -> None:
    from core.agent import goal_source as gs

    root = _repo(tmp_path, {"pkg/__init__.py": "", "pkg/m.py": "def f():\n    return 1\n"})
    goals = {f"fix_{i}": {"id": f"fix_{i}", "kind": "fix_test", "file": "pkg/m.py", "symbol": "f", "via": "sbfl",
                          "nodeid": f"tests/test_m.py::t{i}", "tractability": 0.3} for i in range(4)}
    gs.save_index(root, {"goals": goals, "done": [], "dropped": {}, "cursor": 0,
                         "tries": {"fix_0": 2, "fix_1": 2, "fix_2": 2},
                         # batch 10 item 0: tries carry a timestamp; untimed (pre-batch-10) tries are re-admitted
                         "tries_ts": {f"fix_{i}": gs._now() for i in range(3)}})
    assert gs.next_real(root) is None  # 6 failed tries on pkg/m.py::f retire the whole cluster (until the retry cooldown)


# ---------------------------------------------------------------- learning summary (gap 6)

def test_learning_summary_is_capped_and_secret_free(tmp_path: Path) -> None:
    from core.agent import outcome

    path = outcome.traj_path(tmp_path)
    path.parent.mkdir(parents=True)
    rows = []
    for i in range(300):
        rows.append({"ts": f"2026-11-19T00:00:{i % 60:02d}+00:00", "goal": f"fix_t{i}", "arm": "default" if i % 2 else "minimal",
                     "kind": "pass" if i % 3 == 0 else "fail", "reward": 0.75 if i % 3 == 0 else -0.9,
                     "goal_kind": "fix_test", "regressions": i % 2, "prompt_chars": 900, "spoiler": False,
                     "reply_tail": "ghp_SECRETSECRETSECRET token=abc", "tools": ["search"]})
    rows[-1]["goal"] = "x" * 500 + " ghp_leak https://x-access-token:abc@github.com"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = outcome.publish_summary(tmp_path)
    text = (tmp_path / outcome.SUMMARY_PATH).read_text(encoding="utf-8")
    assert out["ok"] and len(text.encode("utf-8")) <= outcome.SUMMARY_MAX_BYTES
    assert "SECRET" not in text and "reply_tail" not in text and "x-access-token:abc@" not in text
    doc = json.loads(text)
    assert doc["totals"]["graded"] == 300 and doc["totals"]["real_passes"] == 100
    assert doc["arms"]["fix_test"]["minimal"]["pulls"] == 150
    assert all(len(r.get("goal") or "") <= 80 for r in doc["recent"])


def test_learning_summary_is_published_not_memory() -> None:
    from scripts.origin_publish import PATHS

    assert "artifacts/learning_summary.json" in PATHS
    assert not any(p.startswith("memory/") for p in PATHS)
    host = Path("scripts/host_main.py").read_text(encoding="utf-8")
    assert "publish_summary(root)" in host


# ---------------------------------------------------------------- host import paths (gap 1)

def _defined(rel: str) -> set:
    tree = ast.parse(Path(rel).read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, (ast.If, ast.Try)):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.ClassDef)):
                    names.add(sub.name)
                elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                    names.update((a.asname or a.name).split(".")[0] for a in sub.names)
                elif isinstance(sub, ast.Assign):
                    names.update(t.id for t in sub.targets if isinstance(t, ast.Name))
    return names


@pytest.mark.parametrize("rel", ["scripts/host_main.py", "scripts/host_supervisor.py", "scripts/host_ctl.py"])
def test_every_lazy_import_on_the_host_path_resolves(rel: str) -> None:
    """The live host logged plan_error=ImportError every tick for 12 days because a
    publish deleted core.kernel.plan.heartbeat_plan. Every `from X import Y` in the
    host entry points must name something X defines."""
    if not Path(rel).is_file():
        pytest.skip(f"{rel} not present")
    missing = []
    for node in ast.walk(ast.parse(Path(rel).read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in ("core", "scripts", "gems"):
            mod = node.module.replace(".", "/")
            src = mod + ".py" if Path(mod + ".py").is_file() else mod + "/__init__.py"
            if not Path(src).is_file():
                missing.append(f"{node.module} (module)")
                continue
            have = _defined(src)
            for alias in node.names:
                if alias.name != "*" and alias.name not in have and not Path(mod, alias.name + ".py").is_file():
                    missing.append(f"{node.module}.{alias.name}")
    assert missing == []


# ---------------------------------------------------------------- weak tests (gap 4)

PLAN_SRC = "def other():\n    return 0\n"
PLAN_TESTS = (
    "import pkg.plan as plan\n\n\n"
    "def test_next():\n"
    "    from pkg.plan import step\n"
    "    assert step(stale=True)['next'] is None\n"
    "    assert step(stale=False)['next'] == 'edit'\n\n\n"
    "def test_contract():\n"
    "    for stale in (True, False):\n"
    "        assert plan.step(stale=stale) == {'next': None if stale else 'edit', 'stale': stale}\n"
)
PLAN_CHEAT = "def step(*, stale):\n    return {'next': None if stale else 'edit'}\n"
PLAN_ORACLE = "def step(*, stale):\n    return {'next': None if stale else 'edit', 'stale': stale}\n"


def test_a_cheat_that_passes_one_test_but_not_its_siblings_is_rejected(tmp_path: Path) -> None:
    from core.agent import goal_source as gs
    from core.agent import sota

    root = _repo(tmp_path, {"pkg/__init__.py": "", "pkg/plan.py": PLAN_SRC, "tests/test_plan.py": PLAN_TESTS})
    gs.scan(root, n_files=5)
    goals = gs.load_index(root)["goals"]
    assert {g["symbol"] for g in goals.values()} == {"step"} and len(goals) == 2  # ImportError + module attr
    row = sota.run(root, lambda prompt, n=240: PLAN_CHEAT)
    assert row["kept_n"] == 0 and row["note"] == "siblings failed"
    assert (root / "pkg" / "plan.py").read_text(encoding="utf-8") == PLAN_SRC
    data = gs.load_index(root)
    data["tries"] = {}
    gs.save_index(root, data)
    row = sota.run(root, lambda prompt, n=240: PLAN_ORACLE)
    assert row["kept_n"] == 1
    assert gs.load_index(root)["goals"] == {}  # the sibling is resolved by the same edit


def test_ruff_is_found_next_to_the_interpreter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    from core.agent import goal_source as gs

    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "python").write_text("", encoding="utf-8")
    (fake / "ruff").write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    monkeypatch.setattr(sys, "executable", str(fake / "python"))
    assert gs.ruff_bin() == str(fake / "ruff")
