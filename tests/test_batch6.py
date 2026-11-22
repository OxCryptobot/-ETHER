"""Batch 6: span goals, precise drop labels, assign goals from tests, topology refactor
strategies, first-hour report. Tmp repos only."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def _repo(tmp_path: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


BIG = "def report():\n" + "".join(f"    v{i} = {i}  # padding line {i} to make this function long\n" for i in range(30)) + (
    "    payload = {\n"
    "        \"count\": v1 + v2,\n"
    "        \"resolved\": [\n"
    "            \"dashboard: single control matrix\",\n"
    "            \"latency honesty\",\n"
    "        ],\n"
    "    }\n"
    "    return payload\n")
SPAN_REPO = {
    "pkg/__init__.py": "",
    "pkg/big.py": BIG,
    "tests/test_big.py": ("def test_resolved_mentions_host_first():\n    from pkg.big import report\n"
                          "    resolved = ' '.join(report()['resolved'])\n"
                          "    assert 'host-first' in resolved.lower()\n\n\n"
                          "def test_count():\n    from pkg.big import report\n    assert report()['count'] == 3\n"),
}


def _window(prompt: str) -> list:
    from core.agent import span_edit

    body = prompt.split(span_edit.MARK_START, 1)[1].split("\n", 1)[1].split(span_edit.MARK_END, 1)[0]
    return body.rstrip("\n").split("\n")


def _add_host_first(prompt: str, n: int = 240) -> str:
    out = []
    for ln in _window(prompt):
        out.append(ln)
        if '"resolved": [' in ln:
            out.append(ln[: len(ln) - len(ln.lstrip())] + '    "host-first launch",')
    return "\n".join(out)


def _span_repo(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    monkeypatch.setenv("ETHER_REPLY_MAX", "240")
    root = _repo(tmp_path, SPAN_REPO)
    gs.scan(root, n_files=5)
    return root


def test_too_large_target_becomes_a_span_goal_on_the_assert_literal(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    root = _span_repo(tmp_path, monkeypatch)
    goal = gs.next_real(root)
    assert goal["file"] == "pkg/big.py" and goal["symbol"] == "report"
    sp = goal["span"]
    lines = (root / "pkg/big.py").read_text().splitlines()
    assert '"resolved": [' in lines[sp["anchor"] - 1] and sp["anchor_via"] == "assert_literal"
    assert sp["end"] - sp["start"] + 1 <= 30 and sp["start"] > 1
    assert gs.fits_reply(root, goal)
    prompt = gs.build_prompt(root, goal)
    assert "# >>> EDIT START" in prompt and "Reply with ONLY the replacement" in prompt
    assert "host-first" not in prompt.split("Test:")[0].split("Error")[0]  # goal head carries no answer


def test_span_flag_off_keeps_the_drop(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    monkeypatch.setenv("ETHER_SPAN_EDIT", "0")
    root = _span_repo(tmp_path, monkeypatch)
    assert gs.next_real(root) is None
    assert "too_large" in gs.load_index(root)["dropped"].values()


def test_span_edit_kept_only_when_tests_pass(tmp_path, monkeypatch):
    from core.agent import goal_source as gs
    from core.agent import sota

    root = _span_repo(tmp_path, monkeypatch)
    before = (root / "pkg/big.py").read_text()
    row = sota.run(root, lambda p, n=240: "\n".join(_window(p)).replace("latency honesty", "latency honesty!"))
    assert row["kept_n"] == 0 and (root / "pkg/big.py").read_text() == before
    data = gs.load_index(root)
    data["tries"] = {}
    gs.save_index(root, data)
    row = sota.run(root, _add_host_first)
    assert row["kept_n"] == 1, __import__("json").dumps(row, default=str)[:3000]
    from importlib import util

    spec = util.spec_from_file_location("big_after", root / "pkg/big.py")
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "host-first launch" in mod.report()["resolved"] and mod.report()["count"] == 3


def test_span_apply_guards(tmp_path, monkeypatch):
    from core.agent import goal_source as gs
    from core.agent import span_edit

    root = _span_repo(tmp_path, monkeypatch)
    goal = gs.next_real(root)
    path = root / "pkg/big.py"
    original = path.read_text()
    assert span_edit.apply(root, goal, "")["reason"] == "empty edit"
    assert span_edit.apply(root, goal, "\n".join(_window(gs.build_prompt(root, goal))))["reason"] == "no change"
    assert span_edit.apply(root, goal, "    return (\n")["reason"].startswith("syntax")
    # model replies at column 0: re-indented to the window's indentation
    flat = "\n".join(ln.strip() if not ln.strip().startswith('"') else ln.strip() for ln in _window(gs.build_prompt(root, goal)))
    res = span_edit.apply(root, goal, _add_host_first(gs.build_prompt(root, goal)).replace("\n        ", "\n    ", 0))
    assert res["ok"] and path.read_text() != original
    path.write_text(original)
    # stale: the window changed since the scan
    path.write_text(original.replace("latency honesty", "latency honesty (edited)"))
    assert span_edit.apply(root, goal, "    pass")["reason"] == "stale span"
    path.write_text(original)
    assert flat  # flat text built without error
    prot = {**goal, "file": "core/agent/sota.py"}
    assert span_edit.apply(root, prot, "x = 1")["reason"] == "protected path"


def test_span_reindents_a_flush_left_reply(tmp_path, monkeypatch):
    from core.agent import goal_source as gs
    from core.agent import span_edit

    root = _span_repo(tmp_path, monkeypatch)
    goal = gs.next_real(root)
    import textwrap

    reply = textwrap.dedent(_add_host_first(gs.build_prompt(root, goal)))
    assert not reply.startswith(" ")
    assert span_edit.apply(root, goal, reply)["ok"]
    compile((root / "pkg/big.py").read_text(), "big.py", "exec")


def test_span_extract_takes_text_between_markers():
    from core.agent import span_edit

    reply = f"sure\n```python\n{span_edit.MARK_START} (lines 3-4)\n    a = 1\n    b = 2\n{span_edit.MARK_END}\n```\n"
    assert span_edit.extract(reply) == "    a = 1\n    b = 2"
    assert span_edit.extract("\n\n    x = 1\n\n") == "    x = 1"


def test_frame_line_anchors_the_span(tmp_path, monkeypatch):
    from core.agent import span_edit

    root = _repo(tmp_path, {"pkg/big.py": BIG})
    goal = {"file": "pkg/big.py", "symbol": "report", "nodeid": "t::x"}
    sp = span_edit.make_span(root, goal, "", frame_line=10)["span"]
    assert sp["anchor"] == 10 and sp["anchor_via"] == "frame" and sp["start"] <= 10 <= sp["end"]
    assert span_edit.make_span(root, goal, "nothing relevant here") is None  # no evidence -> no span


# ---------------------------------------------------------------- drop labels / assign goals

def test_name_error_in_the_test_for_a_repo_name_is_a_test_bug(tmp_path):
    from core.agent import goal_source as gs

    root = _repo(tmp_path, {"core/__init__.py": "", "core/stages.py": "STAGE_CODE = 'code'\nSTAGE_PLAN = 'plan'\n",
                            "tests/test_s.py": "from core.stages import STAGE_PLAN\n\n\ndef test_s():\n"
                                               "    assert STAGE_PLAN == 'plan'\n    assert STAGE_CODE\n"})
    text = ("tests/test_s.py:6: in test_s\n    assert STAGE_CODE\n           ^^^^^^^^^^\n"
            "E   NameError: name 'STAGE_CODE' is not defined")
    goal, reason = gs.classify_failure(root, "tests/test_s.py::test_s", text, None)
    assert goal is None and reason == "test_bug"


def test_many_listed_sites_are_too_many_sites_even_with_multi_off(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    monkeypatch.delenv("ETHER_MULTI_EDIT", raising=False)
    files = {f"core/m{i}.py": "import os\n" for i in range(5)}
    files["tests/test_t.py"] = "def test_t():\n    assert False\n"
    root = _repo(tmp_path, files)
    text = "E   assert not\n" + "\n".join(f"E       core/m{i}.py:1 imports gems.x" for i in range(5))
    assert gs.classify_failure(root, "tests/test_t.py::test_t", text, None) == (None, "too_many_sites")


def test_inspect_getsource_asserts_are_source_text(tmp_path):
    from core.agent import goal_source as gs

    root = _repo(tmp_path, {"tests/test_src.py": "import inspect\n\n\ndef test_src():\n"
                                                 "    src = inspect.getsource(object)\n    assert 'walk_plan' in src\n"})
    text = "tests/test_src.py:6: in test_src\n    assert 'walk_plan' in src\nE   AssertionError"
    assert gs.classify_failure(root, "tests/test_src.py::test_src", text, None) == (None, "source_text_assert")


def test_test_imported_constant_becomes_an_assign_goal(tmp_path):
    from core.agent import goal_source as gs

    root = _repo(tmp_path, {"scripts/__init__.py": "",
                            "scripts/foreman.py": "TEMPLATES = [\n    {'id_prefix': 'ss_a'},\n]\n\n\ndef tick():\n    return 1\n",
                            "tests/test_f.py": "from scripts.foreman import TEMPLATES\n\n\ndef test_f():\n"
                                               "    prefixes = {t['id_prefix'] for t in TEMPLATES}\n"
                                               "    assert 'ss_b' in prefixes\n"})
    text = ("tests/test_f.py:6: in test_f\n    assert 'ss_b' in prefixes\n"
            "E   AssertionError: assert 'ss_b' in {'ss_a'}")
    goal, reason = gs.classify_failure(root, "tests/test_f.py::test_f", text, None)
    assert reason == "goal" and goal["via"] == "test_import_assign"
    assert goal["file"] == "scripts/foreman.py" and goal["symbol"] == "TEMPLATES" and goal["symbol_kind"] == "assign"


# ---------------------------------------------------------------- topology refactor strategies

def test_dedent_snippet_candidate_and_apply(tmp_path):
    from core.agent import refactor

    root = _repo(tmp_path, {"scripts/_snip.py": "    def method(self):\n        return 1\n",
                            "scripts/ok.py": "x = 1\n", "scripts/broken.py": "def f(:\n"})
    goals = [g for g in refactor.candidates(root, "dedent_snippet")]
    assert [g["file"] for g in goals] == ["scripts/_snip.py"]
    res = refactor.apply(root, goals[0])
    assert res["ok"] and (root / "scripts/_snip.py").read_text() == "def method(self):\n    return 1\n"


STATE_SRC = '''import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "memory" / "x_state.json"
GRAPH_PATH = ROOT / "memory" / "graph.json"


def save(data):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def where():
    return str(GRAPH_PATH.relative_to(ROOT)).replace("\\\\", "/")


def other(p, data):
    p.write_text(json.dumps(data), encoding="utf-8")
'''


def test_state_writer_rewrite_is_equivalent_and_removes_the_sites(tmp_path, monkeypatch):
    import ast
    import importlib.util
    import sys

    from core.agent import refactor

    root = _repo(tmp_path, {"core/x_state.py": STATE_SRC})
    goals = refactor.candidates(root, "state_writer")
    assert [g["file"] for g in goals] == ["core/x_state.py"]
    data = {"b": [1, 2], "a": {"c": None}}

    def run(src_text, name):
        spec = importlib.util.spec_from_file_location(name, root / "core" / "x_state.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.save(data)
        return (root / "memory" / "x_state.json").read_text(), mod.where()

    old_json, old_where = run(STATE_SRC, "x_state_old")
    (root / "memory" / "x_state.json").unlink()
    res = refactor.apply(root, goals[0])
    assert res["ok"]
    new_src = (root / "core/x_state.py").read_text()
    assert "write_json(STATE_PATH, data)" in new_src and ".as_posix()" in new_src
    assert "p.write_text(json.dumps(data)" in new_src  # no indent=2: not provably equivalent, left alone
    assert refactor.state_sites(ast.parse(new_src)) == []
    new_json, new_where = run(new_src, "x_state_new")
    assert json.loads(new_json) == json.loads(old_json) and new_json == old_json and new_where == old_where


def test_state_writer_skips_gems(tmp_path):
    from core.agent import refactor

    root = _repo(tmp_path, {"gems/g/burst.py": STATE_SRC})
    assert refactor.candidates(root, "state_writer") == []


# ---------------------------------------------------------------- first-hour report

def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@x", "PATH": __import__("os").environ["PATH"], "HOME": str(root)})


def test_first_hour_report_reads_a_ref(tmp_path):
    from scripts import first_hour_report as fh

    root = tmp_path
    (root / "artifacts").mkdir()
    (root / "artifacts" / "host_main.json").write_text(json.dumps(
        {"ts": "2026-11-21T18:00:00+00:00", "health": "ok", "plan_error": None, "next_goal": "fix_x",
         "seed_depth": 3, "sota": {"ok": True, "note": "kept", "kept_n": 1}}))
    summary = {
        "schema": 2, "generated": "2026-11-21T18:00:00+00:00",
        "totals": {"graded": 10, "real_graded": 8, "real_passes": 3, "spoiler_share": 0.0},
        "metrics": {"attempts": 8, "kept": 3, "kept_per_attempt": 0.375, "revert_rate": 0.5, "regressions_caught": 2,
                    "by_via": {"sbfl": {"attempts": 5, "kept": 2}, "frame": {"attempts": 3, "kept": 1}}},
        "bandit": {"algo": {"fix_test": "thompson"},
                   "fix_test": {"all": {"arms": {"plain": {"n": 6, "passes": 2, "post_mean": 0.375},
                                                 "repair_heavy": {"n": 2, "passes": 1, "post_mean": 0.5}}}}},
        "recent": [{"goal_kind": "fix_test", "kind": "pass"}, {"goal_kind": "fix_test", "kind": "fail"},
                   {"goal_kind": "lint", "kind": "pass"}],
    }
    (root / "artifacts" / "learning_summary.json").write_text(json.dumps(summary))
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "1650 host_main")
    _git(root, "commit", "-q", "--allow-empty", "-m", "medic")
    doc = fh.report("HEAD", "1 hour ago", root)
    ls = doc["learning"]
    assert doc["host"]["next_goal"] == "fix_x" and doc["host"]["kept_n"] == 1
    assert ls["kept_per_attempt"] == 0.375 and ls["revert_rate"] == 0.5
    assert ls["by_kind_recent"] == {"fix_test": {"attempts": 2, "passes": 1}, "lint": {"attempts": 1, "passes": 1}}
    a = ls["arms"]["fix_test"]
    assert a["pulls"] == {"plain": 6, "repair_heavy": 2} and a["top_share"] == 0.75 and a["arms_used"] == 2
    assert doc["commits"]["n"] == 2 and doc["commits"]["host_main"] == 1
    text = fh.render(doc)
    assert "kept/attempt=0.375" in text and "arms[fix_test]" in text and "fix_test 1/2" in text


def test_first_hour_report_flags_the_old_schema(tmp_path):
    from scripts import first_hour_report as fh

    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "learning_summary.json").write_text(json.dumps({"day": "2026-11-19", "goals": ["a"]}))
    doc = fh.report(None, "1 hour ago", tmp_path)
    assert doc["learning"]["schema"] == "old" and doc["host"] == {"present": False}
    assert "OLD schema" in fh.render(doc)


# ---------------------------------------------------------------- gate robustness

def test_gate_never_tests_stale_bytecode_after_a_same_size_rewrite(tmp_path):
    """Edit -> test -> revert -> same-length edit within one second used to run the first edit's .pyc."""
    import os

    from core.agent import goal_source as gs

    root = _repo(tmp_path, {"pkg/__init__.py": "", "tests/test_d.py": "from pkg.m import double\n\n\n"
                                                                         "def test_d():\n    assert double(4) == 8\n"})
    mod = root / "pkg" / "m.py"
    mod.write_text("def double(x):\n    return x + 2\n")
    first = gs.run_pytest(root, ["tests/test_d.py"])["status"]
    st = os.stat(mod)
    mod.write_text("def double(x):\n    return 2 * x\n")  # same size
    os.utime(mod, (st.st_atime, st.st_mtime))  # same mtime: the worst case CPython cannot see
    second = gs.run_pytest(root, ["tests/test_d.py"])["status"]
    assert first == {"tests/test_d.py::test_d": "fail"} and second == {"tests/test_d.py::test_d": "pass"}


def test_span_window_survives_the_no_context_arm(tmp_path, monkeypatch):
    """Found in batch 6: the no_context ablation arm hid the span window, so a span goal could never be
    answered under that arm (note 'no function'; the span-kept test flaked ~1 in 3 on the arm draw)."""
    from types import SimpleNamespace

    from core.agent import goal_source as gs
    from core.agent import span_edit

    root = _span_repo(tmp_path, monkeypatch)
    goal = gs.next_real(root)
    bare = gs.build_prompt(root, goal, SimpleNamespace(use_workspace_context=False, prompt_addon=""))
    full = gs.build_prompt(root, goal, SimpleNamespace(use_workspace_context=True, prompt_addon=""))
    window = span_edit.span_text(root, goal)
    for prompt in (bare, full):
        assert span_edit.MARK_START in prompt and span_edit.MARK_END in prompt and window in prompt
    assert "def report" not in bare and "def report" in full  # no_context still drops the surroundings
