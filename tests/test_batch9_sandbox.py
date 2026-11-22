"""Batch 9 item 2: gate hardening. Sandbox copy + scrubbed env, timeouts abort, wider guard.

Tmp repos and a scripted mock model only."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_batch7_exemplars import B_GOOD, TESTS_B, _goal, _repo, _run_until


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path_factory):
    for k in ("ETHER_SAMPLE_TEMP", "ETHER_DEDUP_REPLY", "ETHER_EXEMPLARS", "ETHER_BANDIT", "ETHER_SOTA_EXPLORE",
              "ETHER_REFACTOR", "ETHER_MULTI_EDIT", "ETHER_NEURO_ES", "ETHER_BANDIT_FACTORED", "ETHER_GUARD_SUITE",
              "ETHER_GATE_SANDBOX", "ETHER_GUARD_TRANSITIVE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ETHER_REAL_PER_TICK", "1")
    monkeypatch.setenv("ETHER_BANDIT_ARMS", "default")
    monkeypatch.setenv("ETHER_GATE_SANDBOX_DIR", str(tmp_path_factory.mktemp("gate")))


def test_scrub_env_drops_credentials_and_blocks_proxies():
    from core.agent.gate_sandbox import DEAD_PROXY, scrub_env

    env = scrub_env({"PATH": "/bin", "GH_TOKEN": "t", "GITHUB_TOKEN": "t", "ETHER_GH_TOKEN": "t",
                     "AWS_SECRET_ACCESS_KEY": "k", "OPENAI_API_KEY": "k", "HTTPS_PROXY": "http://corp:8080",
                     "ETHER_REAL_PER_TICK": "2", "MY_PASSWORD": "p", "GIT_ASKPASS": "/x"})
    assert env["PATH"] == "/bin" and env["ETHER_REAL_PER_TICK"] == "2"
    for k in ("GH_TOKEN", "GITHUB_TOKEN", "ETHER_GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY", "MY_PASSWORD",
              "GIT_ASKPASS"):
        assert k not in env, k
    assert env["HTTPS_PROXY"] == DEAD_PROXY and env["GIT_TERMINAL_PROMPT"] == "0"


def _mini(tmp_path: Path, test_src: str) -> Path:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "m.py").write_text("V = 1\n", encoding="utf-8")
    (root / "tests" / "test_m.py").write_text(test_src, encoding="utf-8")
    return root


def test_gate_runs_in_a_copy_without_the_token(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    monkeypatch.setenv("GH_TOKEN", "ghp_should_not_leak")
    src = ("import os, pathlib\n\n\ndef test_env():\n    assert 'GH_TOKEN' not in os.environ\n"
           "    assert os.environ.get('ETHER_GATE_SANDBOXED') == '1'\n"
           "    assert pathlib.Path.cwd().resolve() != pathlib.Path(%r).resolve()\n") % str(tmp_path / "repo")
    root = _mini(tmp_path, src)
    res = gs.run_pytest(root, ["tests/test_m.py"])
    assert res["sandbox"] is True and res["status"] == {"tests/test_m.py::test_env": "pass"}, res
    assert res["tamper"] == []


def test_a_run_that_writes_the_tree_only_changes_the_copy_and_is_reported(tmp_path):
    from core.agent import goal_source as gs

    src = ("import pathlib\n\n\ndef test_w():\n    pathlib.Path('pkg/m.py').write_text('V = 2\\n')\n"
           "    pathlib.Path('tests/test_new.py').write_text('')\n")
    root = _mini(tmp_path, src)
    res = gs.run_pytest(root, ["tests/test_m.py"])
    assert (root / "pkg" / "m.py").read_text(encoding="utf-8") == "V = 1\n"
    assert not (root / "tests" / "test_new.py").exists()
    assert res["tamper"] == ["pkg/m.py", "tests/test_new.py"]
    res2 = gs.run_pytest(root, ["tests/test_m.py"])  # the next sync resets the copy
    assert res2["status"] and res2["tamper"] == ["pkg/m.py", "tests/test_new.py"]


def test_candidate_rewriting_its_test_in_the_sandbox_is_rejected(tmp_path):
    root = _repo(tmp_path)
    cheat = ("def floor_at(value, floor):\n    import pathlib\n"
             "    pathlib.Path('tests/test_b.py').write_text('def test_b():\\n    pass\\n')\n"
             "    return max(value, floor)\n")
    rows = _run_until(root, lambda p, n=240: cheat, "floor_at", n=2)
    assert not any(r.get("ok") for r in rows), rows
    assert any("tests/test_b.py" in str(r.get("note")) for r in rows), rows
    assert (root / "tests/test_b.py").read_text(encoding="utf-8") == TESTS_B
    assert "return value\n" in (root / "pkg/b.py").read_text(encoding="utf-8")


def test_baseline_timeout_aborts_without_a_model_call_and_reward_zero(tmp_path, monkeypatch):
    from core.agent import goal_source as gs
    from core.agent.outcome import trajectories

    root = _repo(tmp_path)
    gid = _goal(root, "floor_at")["id"]
    monkeypatch.setattr(gs, "run_pytest", lambda *a, **k: {"ok": False, "rc": -9, "status": {}, "fail": {},
                                                           "secs": 180.0, "timeout": True})
    calls = []
    rows = _run_until(root, lambda p, n=240: calls.append(p) or B_GOOD, "floor_at", n=1)
    assert rows[-1]["ok"] is False and rows[-1]["note"] == "gate aborted: baseline timeout"
    assert calls == []
    assert "return value\n" in (root / "pkg/b.py").read_text(encoding="utf-8")
    traj = [t for t in trajectories(root) if t.get("goal") == gid]
    assert traj and traj[-1]["reward01"] == 0


def test_after_run_timeout_is_never_a_pass(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    real = gs.run_pytest
    n = {"i": 0}

    def flaky(*a, **k):
        n["i"] += 1
        if n["i"] == 1:
            return real(*a, **k)
        return {"ok": False, "rc": -9, "status": {}, "fail": {}, "secs": 180.0, "timeout": True}

    monkeypatch.setattr(gs, "run_pytest", flaky)
    rows = _run_until(root, lambda p, n=240: B_GOOD, "floor_at", n=1)
    assert rows[-1]["ok"] is False and rows[-1]["note"] == "gate aborted: after-run timeout", rows
    assert "return value\n" in (root / "pkg/b.py").read_text(encoding="utf-8")


def test_empty_baseline_never_disables_the_regression_check(tmp_path):
    from core.agent import goal_source as gs

    root = _repo(tmp_path)
    goal = _goal(root, "floor_at")
    v = gs.gate(root, goal, {}, [goal["test_file"]])
    assert v["ok"] is False and v["abort"] == "empty baseline"
    assert gs.baseline_abort({"status": {}, "rc": 1}) == "baseline produced no test results"
    assert gs.baseline_abort({"status": {"a": "pass"}, "rc": 0}) == ""


def _wide_repo(tmp_path: Path) -> Path:
    root = _repo(tmp_path)
    (root / "pkg" / "c.py").write_text("from pkg.b import floor_at\n\n\ndef at_least_one(v):\n"
                                       "    return floor_at(v, 1) - 0\n", encoding="utf-8")
    (root / "pkg" / "d.py").write_text("from pkg import c\n\n\ndef twice(v):\n    return 2 * c.at_least_one(v)\n",
                                       encoding="utf-8")
    (root / "tests" / "test_d.py").write_text("from pkg.d import twice\n\n\ndef test_twice_keeps_big_values():\n"
                                              "    assert twice(7) == 14\n", encoding="utf-8")
    return root


def test_guard_runs_transitive_importers_and_a_fixed_sample(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    root = _wide_repo(tmp_path)
    goal = _goal(root, "floor_at")
    suite = gs.guard_suite(root, goal)
    assert "tests/test_d.py" in suite  # imports pkg.d -> pkg.c -> pkg.b (two hops)
    assert suite == gs.guard_suite(root, goal)  # fixed: same goal, same files
    monkeypatch.setenv("ETHER_GUARD_TRANSITIVE", "0")
    assert "tests/test_d.py" not in gs.guard_suite(root, goal)  # batch 8 selection missed it


def test_regression_two_imports_away_is_caught(tmp_path):
    """Audit W5 scenario: the edit passes its own test and breaks a test two imports away."""
    root = _wide_repo(tmp_path)
    breaks_d = "def floor_at(value, floor):\n    return max(value, floor) if value < floor else floor\n"
    rows = _run_until(root, lambda p, n=240: breaks_d, "floor_at", n=1)
    assert rows[-1]["ok"] is False and rows[-1]["note"] == "regression", rows
    assert "return value\n" in (root / "pkg/b.py").read_text(encoding="utf-8")
    rows = _run_until(root, lambda p, n=240: B_GOOD, "floor_at", n=1)
    assert rows[-1]["ok"] is True


def test_mirror_is_never_inside_the_repo(tmp_path, monkeypatch):
    from core.agent import gate_sandbox

    monkeypatch.setenv("ETHER_GATE_SANDBOX_DIR", str(tmp_path / "inside"))
    d = gate_sandbox.mirror_dir(tmp_path)
    with pytest.raises(ValueError):
        d.relative_to(tmp_path.resolve())
