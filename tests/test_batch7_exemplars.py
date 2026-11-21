"""Batch 7: kept-edit exemplars (ETHER_EXEMPLARS). Tmp repos and a mock model only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

A_BUG = "def clamp_low(x, lo):\n    return x\n"
B_BUG = "def floor_at(value, floor):\n    return value\n"
A_GOOD = "def clamp_low(x, lo):\n    return max(x, lo)\n"
B_GOOD = "def floor_at(value, floor):\n    return max(value, floor)\n"
B_WRONG = "def floor_at(value, floor):\n    return value + 0\n"
TESTS_A = "from pkg.a import clamp_low\n\n\ndef test_clamp_low_raises_small_values():\n    assert clamp_low(1, 5) == 5\n    assert clamp_low(9, 5) == 9\n"
TESTS_B = "from pkg.b import floor_at\n\n\ndef test_floor_at_raises_small_values():\n    assert floor_at(1, 5) == 5\n    assert floor_at(9, 5) == 9\n"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("ETHER_EXEMPLARS", "ETHER_BANDIT_ARMS", "ETHER_BANDIT", "ETHER_SOTA_EXPLORE", "ETHER_REFACTOR",
              "ETHER_MULTI_EDIT", "ETHER_NEURO_ES", "ETHER_BANDIT_FACTORED"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ETHER_REAL_PER_TICK", "1")


def _repo(tmp_path: Path) -> Path:
    files = {"pkg/__init__.py": "", "pkg/a.py": A_BUG, "pkg/b.py": B_BUG,
             "tests/test_a.py": TESTS_A, "tests/test_b.py": TESTS_B}
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (tmp_path / "artifacts").mkdir()
    from core.agent import goal_source as gs

    gs.scan(tmp_path, n_files=10)
    return tmp_path


class PatternCopier:
    """A mock 4B: fixes clamp_low on its own; fixes floor_at only when a kept diff shows the max() pattern."""

    def __init__(self):
        self.prompts = []

    def __call__(self, prompt: str, n: int = 240) -> str:
        self.prompts.append(prompt)
        if "clamp_low" in prompt.split("Test:")[0]:
            return A_GOOD
        from core.agent.goal_source import EXEMPLAR_HEAD

        if EXEMPLAR_HEAD in prompt and "+    return max(" in prompt:
            return B_GOOD
        return B_WRONG


def _force_arm(monkeypatch, want: str):
    """Pick `want` whenever the selector is allowed to (the real arm filter still runs first)."""
    from core.agent import bandit

    real = bandit.select

    def pick(name, stats, arm_list, rng, cost=False):
        if want in arm_list:
            return want, "forced"
        return real(name, stats, arm_list, rng, cost)

    monkeypatch.setattr(bandit, "select", pick)


def _goal(root, symbol):
    from core.agent import goal_source as gs

    return next(g for g in gs.load_index(root)["goals"].values() if g["symbol"] == symbol)


def _run_until(root, ask, symbol, n=4):
    from core.agent import goal_source as gs
    from core.agent import sota

    rows = []
    for _ in range(n):
        g = _goal(root, symbol)
        others = [x["id"] for x in gs.load_index(root)["goals"].values() if x["id"] != g["id"]]
        rows.append(sota._one(root, ask, skip=others))
        if rows[-1].get("ok") or rows[-1].get("note") == "queue empty":
            break
    return rows


def test_flag_off_writes_nothing_and_prompts_are_unchanged(tmp_path, monkeypatch):
    from core.agent import exemplars, goal_source as gs

    root = _repo(tmp_path)
    goal = _goal(root, "floor_at")
    p0 = gs.build_prompt(root, goal)
    p1 = gs.build_prompt(root, goal, None, exemplar=[{"id": "x", "diff": "+    return max(a, b)", "error_kind": "AssertionError"}])
    assert p0 == p1  # no behaviour with use_exemplars -> byte-identical
    ask = PatternCopier()
    _run_until(root, ask, "clamp_low")
    assert exemplars.mode() == "0" and not exemplars.path(root).exists()
    from core.agent import bandit

    assert "exemplar" not in bandit.arms()


def test_record_mode_stores_only_gate_kept_edits(tmp_path, monkeypatch):
    from core.agent import exemplars

    monkeypatch.setenv("ETHER_EXEMPLARS", "record")
    root = _repo(tmp_path)
    ask = PatternCopier()
    rows = _run_until(root, ask, "floor_at")  # B_WRONG every time: never kept
    assert not any(r.get("ok") for r in rows)
    assert exemplars.load(root) == []
    rows = _run_until(root, ask, "clamp_low")
    assert rows[-1]["ok"] and rows[-1]["regressions"] == 0
    lib = exemplars.load(root)
    assert len(lib) == 1 and lib[0]["symbol"] == "clamp_low" and "+    return max(x, lo)" in lib[0]["diff"]
    from core.agent.goal_source import EXEMPLAR_HEAD
    from core.agent import bandit

    assert all(EXEMPLAR_HEAD not in p for p in ask.prompts)  # record never injects
    assert "exemplar" not in bandit.arms()
    assert exemplars.record_kept(root, _goal(root, "floor_at"), B_BUG, B_GOOD, {"ok": False}) is None


def test_mock_replay_exemplar_arm_turns_a_miss_into_a_keep(tmp_path, monkeypatch):
    """Same mock model, same goals: flag off -> floor_at never kept; flag 1 -> kept via the shown diff."""
    from core.agent import exemplars, goal_source as gs
    from core.agent.outcome import trajectories

    # control
    monkeypatch.setenv("ETHER_EXEMPLARS", "record")
    ctl = _repo(tmp_path / "ctl")
    _run_until(ctl, PatternCopier(), "clamp_low")
    rows = _run_until(ctl, PatternCopier(), "floor_at")
    assert not any(r.get("ok") for r in rows)
    # treatment
    monkeypatch.setenv("ETHER_EXEMPLARS", "1")
    _force_arm(monkeypatch, "exemplar")
    root = _repo(tmp_path / "trt")
    clamp_id = _goal(root, "clamp_low")["id"]
    ask = PatternCopier()
    first = _run_until(root, ask, "clamp_low")
    assert first[-1]["ok"]
    assert first[0].get("learn", {}).get("arm") != "exemplar"  # empty library: arm not offered
    rows = _run_until(root, ask, "floor_at")
    assert rows[-1]["ok"] and rows[-1]["regressions"] == 0, json.dumps(rows, default=str)[:2000]
    assert rows[-1]["learn"]["arm"] == "exemplar" and rows[-1]["learn"]["reward"] is not None
    traj = [t for t in trajectories(root) if t.get("goal") == rows[-1]["goal"]]
    assert traj[-1]["exemplar"] == clamp_id and traj[-1]["reward01"] == 1
    assert traj[-1]["exemplar_eligible"] is True
    first_traj = [t for t in trajectories(root) if t.get("goal") == clamp_id]
    assert first_traj and first_traj[0]["exemplar_eligible"] is False  # empty library at the first goal
    assert "def floor_at(value, floor):\n    return max(value, floor)" in (root / "pkg/b.py").read_text()
    lib = {r["symbol"]: r for r in exemplars.load(root)}
    assert set(lib) == {"clamp_low", "floor_at"} and lib["clamp_low"]["uses"] == 1
    s = exemplars.summary(root)
    assert s["library"] == 2 and s["shown"] == 1 and s["kept_when_shown"] == 1
    from core.agent.outcome import summary_doc

    assert summary_doc(root)["exemplars"]["kept_when_shown"] == 1


def test_a_wrong_reply_after_an_exemplar_is_still_reverted(tmp_path, monkeypatch):
    from core.agent import goal_source as gs

    monkeypatch.setenv("ETHER_EXEMPLARS", "1")
    _force_arm(monkeypatch, "exemplar")
    root = _repo(tmp_path)
    _run_until(root, PatternCopier(), "clamp_low")
    rows = _run_until(root, lambda p, n=240: B_WRONG, "floor_at", n=2)
    assert not any(r.get("ok") for r in rows)
    assert (root / "pkg/b.py").read_text() == B_BUG


def test_leak_rules():
    from core.agent import exemplars as ex

    goal = {"id": "g1", "nodeid": "tests/t.py::test_x", "file": "pkg/m.py", "symbol": "Cls.parse",
            "error_kind": "AssertionError", "error": "assert parse('a') == 1"}
    assert ex.leaks(goal, {"id": "g1", "diff": "+x"})
    assert ex.leaks(goal, {"id": "g2", "nodeid": "tests/t.py::test_x", "diff": "+x"})
    assert ex.leaks(goal, {"id": "g3", "file": "pkg/m.py", "symbol": "Cls.parse", "diff": "+x"})
    assert ex.leaks(goal, {"id": "g4", "file": "pkg/o.py", "symbol": "other", "diff": " def parse(s):\n+    return 1"})
    assert ex.leaks(goal, {"id": "g5", "file": "pkg/o.py", "symbol": "parse", "diff": "-parse = 0\n+parse = 1"})
    assert not ex.leaks(goal, {"id": "g6", "file": "pkg/o.py", "symbol": "other",
                               "diff": " def other(s):\n-    return s\n+    return parse(s)"})


def test_retrieval_prefers_shared_rare_words_and_respects_min_score():
    from core.agent import exemplars as ex

    goal = {"id": "q", "file": "pkg/q.py", "symbol": "budget_of", "error_kind": "AssertionError",
            "nodeid": "tests/test_ctx.py::test_budget_of_small_context", "error": "assert budget_of(100) >= 800 context"}
    near = {"id": "a", "file": "pkg/a.py", "symbol": "room_left", "error_kind": "AssertionError", "kind": "fix_test",
            "tokens": ex.tokens("AssertionError", "context budget room", "test_room_left_context_budget", "room_left"),
            "diff": "+    return max(0, budget - used)", "kept": True}
    far = {"id": "b", "file": "pkg/b.py", "symbol": "render_html", "error_kind": "TypeError", "kind": "fix_test",
           "tokens": ex.tokens("TypeError", "html template", "test_render_html", "render_html"),
           "diff": "+    return tpl.format(**kw)", "kept": True}
    got = ex.retrieve(Path("."), goal, k=2, rows=[far, near])
    assert got and got[0]["id"] == "a"
    assert all(r["id"] != "b" for r in got)  # below MIN_SCORE: no unrelated hint


@pytest.mark.parametrize("ctx", ["2048", "4096", "8192"])
def test_block_fits_the_context_budget_and_passes_the_spoiler_guard(tmp_path, monkeypatch, ctx):
    from core.agent import exemplars, goal_source as gs
    from core.agent.goal_quality import check
    from core.kernel.context_budget import context_char_budget

    monkeypatch.setenv("ETHER_MODEL_CTX", ctx)
    root = _repo(tmp_path)
    goal = _goal(root, "floor_at")
    big = {"id": "k", "file": "pkg/a.py", "symbol": "clamp_low", "error_kind": "AssertionError", "error": "e" * 400,
           "diff": "\n".join(f"+    line_{i} = max(x, lo)  # padding" for i in range(60)), "kept": True}
    prompt = gs.build_prompt(root, goal, exemplars.behaviour(), exemplar=[big])
    assert len(prompt) <= context_char_budget()
    assert gs.EXEMPLAR_HEAD in prompt
    blk = prompt.split(gs.EXEMPLAR_HEAD, 1)[1]
    assert len(gs.EXEMPLAR_HEAD) + len(blk.split("pkg/b.py (current)")[0]) <= exemplars.BLOCK_CAP + 2
    assert check(goal, prompt, (root / goal["file"]).read_text())["ok"]


def test_first_hour_report_prints_the_exemplar_line():
    import importlib.util

    spec = importlib.util.spec_from_file_location("fhr7", Path(__file__).resolve().parents[1] / "scripts/first_hour_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ls = mod.learning_view({"schema": 2, "totals": {"graded": 4}, "metrics": {}, "bandit": {},
                            "exemplars": {"mode": "1", "library": 3, "shown": 2, "kept_when_shown": 1,
                                          "kept_per_attempt_shown": 0.5, "kept_per_attempt_other": 0.25,
                                          "reuse_rate": 0.6667}})
    doc = {"ref": "x", "head": "h", "host": {"present": False}, "learning": ls,
           "commits": {"n": 0, "per_hour": 0, "window_h": 1}}
    text = mod.render(doc)
    assert "exemplars[1]: library 3  shown 2  kept/attempt shown 0.500 vs other 0.250  reuse 0.667" in text


@pytest.mark.parametrize("ctx", ["2048", "4096"])
def test_exemplar_never_squeezes_the_span_window(tmp_path, monkeypatch, ctx):
    """A span goal must still show its whole marked window when the hint is added."""
    from core.agent import exemplars, goal_source as gs, span_edit
    from tests.test_batch6 import SPAN_REPO, _repo as repo6

    monkeypatch.setenv("ETHER_MODEL_CTX", ctx)
    monkeypatch.setenv("ETHER_REPLY_MAX", "240")
    root = repo6(tmp_path, SPAN_REPO)
    gs.scan(root, n_files=5)
    goal = gs.next_real(root)
    assert goal and goal.get("span")
    row = {"id": "k", "file": "pkg/other.py", "symbol": "other", "error_kind": "AssertionError", "error": "e" * 200,
           "diff": "\n".join(f"+    line_{i} = 1  # padding padding" for i in range(40)), "kept": True}
    base = gs.build_prompt(root, goal)
    with_hint = gs.build_prompt(root, goal, exemplars.behaviour(), exemplar=[row])
    win = base.split(span_edit.MARK_START, 1)[1].split(span_edit.MARK_END, 1)[0]
    assert win in with_hint  # window intact
