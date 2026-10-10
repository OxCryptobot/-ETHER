"""The product path keeps an edit only when tests pass, and generate is not honest."""
from pathlib import Path

from core.kernel.context_budget import pack
from core.kernel.product_loop import run_edit, run_model_edit
from core.kernel.subagent import isolate


def test_revert_keeps_the_worktree_git_dir(tmp_path: Path) -> None:
    from core.kernel.edit_tx import EditTx

    ws = tmp_path / "edit_ws"
    git = ws / ".git" / "objects"
    git.mkdir(parents=True)
    (git / "pack").write_text("keep", encoding="utf-8")
    (ws / "ends.py").write_text("def ends(s):\n    return s[:1]\n", encoding="utf-8")
    tx = EditTx(ws, tmp_path / "edit_ws.snap")
    tx.begin()
    assert not (tmp_path / "edit_ws.snap" / ".git").exists()
    (ws / "ends.py").write_text("broken\n", encoding="utf-8")
    tx.revert()
    assert (git / "pack").read_text(encoding="utf-8") == "keep"
    assert "return s[:1]" in (ws / "ends.py").read_text(encoding="utf-8")


def test_a_stale_snapshot_git_dir_is_wiped(tmp_path: Path) -> None:
    from core.kernel.edit_tx import EditTx

    ws = tmp_path / "edit_ws"
    (ws / ".git").mkdir(parents=True)
    (ws / "a.py").write_text("one\n", encoding="utf-8")
    snap = tmp_path / "edit_ws.snap"
    obj = snap / ".git" / "objects"
    obj.mkdir(parents=True)
    (obj / "x").write_text("old", encoding="utf-8")
    (snap / "a.py").write_text("stale\n", encoding="utf-8")
    tx = EditTx(ws, snap)
    tx.begin()
    assert not (snap / ".git").exists()
    (ws / "a.py").write_text("new\n", encoding="utf-8")
    tx.revert()
    assert (ws / "a.py").read_text(encoding="utf-8") == "one\n"
    assert (ws / ".git").is_dir()


def test_two_files_revert_together(tmp_path: Path) -> None:
    from core.kernel.product_loop import files_from_reply, run_files_edit

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "person.py").write_text("def person():\n    return ''\n", encoding="utf-8")
    (ws / "greet.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
    reply = "def person():\n    return 'ada'\n\ndef greet():\n    return 'hi ada'\n"
    assert files_from_reply(reply, {"person": "person.py"}) is None
    mapping = files_from_reply(reply, {"person": "person.py", "greet": "greet.py"})
    assert mapping is not None and set(mapping) == {"person.py", "greet.py"}

    def fail() -> bool:
        return False

    bad = run_files_edit(ws, mapping, fail)
    assert bad["honest"] is False
    assert "revert" in bad["tx"]
    assert (ws / "person.py").read_text(encoding="utf-8") == "def person():\n    return ''\n"
    assert (ws / "greet.py").read_text(encoding="utf-8") == "def greet():\n    return 'hi'\n"

    good_reply = "def person():\n    return 'ada'\n\ndef greet():\n    return 'hi ' + person()\n"
    good_map = files_from_reply(good_reply, {"person": "person.py", "greet": "greet.py"})
    assert good_map is not None

    def tests_ok() -> bool:
        ns: dict = {}
        exec((ws / "person.py").read_text(encoding="utf-8"), ns)
        exec((ws / "greet.py").read_text(encoding="utf-8"), ns)
        return ns["person"]() == "ada" and ns["greet"]() == "hi ada"

    row = run_files_edit(ws, good_map, tests_ok)
    assert row["honest"] is True
    assert row["tests_ok"] is True
    assert "promote" in row["tx"]
    assert len(row["files"]) == 2
    assert (ws / "person.py").read_text(encoding="utf-8").startswith("def person")
    assert "person()" in (ws / "greet.py").read_text(encoding="utf-8")


def test_dropping_the_old_fix_does_not_land(tmp_path: Path) -> None:
    from core.kernel.product_loop import apply_reply

    ws = tmp_path / "ws"
    ws.mkdir()
    original = "def merge_intervals(intervals):\n    return list(intervals)\n\ndef adjacent(a, b):\n    return False\n"
    (ws / "intervals.py").write_text(original, encoding="utf-8")
    parts = {"merge_intervals": "intervals.py", "adjacent": "intervals.py"}
    missing = apply_reply(ws, "intervals.py", "def adjacent(a, b):\n    return True\n", lambda: True, parts)
    assert missing["reason"] == "no_tool_edit"
    assert (ws / "intervals.py").read_text(encoding="utf-8") == original
    both = (
        "def merge_intervals(intervals):\n"
        "    return []\n"
        "def adjacent(a, b):\n"
        "    return a[1] >= b[0] and b[1] >= a[0]\n"
    )
    row = apply_reply(ws, "intervals.py", both, lambda: False, parts)
    assert row["honest"] is False
    assert "revert" in row["tx"]
    assert (ws / "intervals.py").read_text(encoding="utf-8") == original



def test_prose_is_not_a_pass(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "add.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    row = run_model_edit(ws, "add.py", "I would add the numbers together.", lambda: True)
    assert row["honest"] is False
    assert row["strategy"] == "generate"
    assert "return a - b" in (ws / "add.py").read_text(encoding="utf-8")


def test_a_complete_function_is_kept_only_when_tests_pass(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "bounds.py").write_text("def span(nums):\n    return 0\n", encoding="utf-8")
    good = "def span(nums):\n    return (max(nums) - min(nums)) if nums else 0\n"

    def tests_ok() -> bool:
        ns: dict = {}
        exec(compile((ws / "bounds.py").read_text(encoding="utf-8"), "bounds.py", "exec"), ns, ns)
        return ns["span"]([1, 4, 2]) == 3 and ns["span"]([]) == 0

    row = run_model_edit(ws, "bounds.py", good, tests_ok)
    assert row["honest"] is True
    assert row["tools"] == ["replace_file"]
    assert "promote" in row["tx"]
    bad = run_model_edit(ws, "bounds.py", "def span(nums):\n    return 1\n", lambda: False)
    assert bad["honest"] is False
    assert "revert" in bad["tx"]
    assert "return 0" not in (ws / "bounds.py").read_text(encoding="utf-8")
    cut = run_model_edit(ws, "bounds.py", "def span(nums):\n    for n in nums:\n        if n <", lambda: True)
    assert cut["reason"] == "no_tool_edit"
    assert cut["honest"] is False


def test_tool_edit_promotes_only_when_tests_pass(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "add.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    text = "OLD: return a - b\nNEW: return a + b\n"

    def tests_ok() -> bool:
        ns: dict = {}
        exec(compile((ws / "add.py").read_text(encoding="utf-8"), "add.py", "exec"), ns, ns)
        return ns["add"](2, 3) == 5

    row = run_model_edit(ws, "add.py", text, tests_ok)
    assert row["ok"] is True
    assert row["honest"] is True
    assert row["tools"] == ["replace_once"]
    assert "return a + b" in (ws / "add.py").read_text(encoding="utf-8")


def test_failed_test_reverts(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "add.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    row = run_edit(ws, "add.py", "return a - b", "return a + b", lambda: False)
    assert row["honest"] is False
    assert "return a - b" in (ws / "add.py").read_text(encoding="utf-8")


def test_pack_keeps_named_file_inside_budget(tmp_path: Path) -> None:
    (tmp_path / "add.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    text = pack(tmp_path, "add", ["add.py"], max_chars=500)
    assert "add.py" in text
    assert len(text) <= 500


def test_subagent_does_not_share_the_parent_dict() -> None:
    parent = {"secret": "no"}

    def child(box):
        box["secret"] = "changed"
        return box["goal"]

    out = isolate("fix add", "add.py", child)
    assert out["ok"] is True
    assert out["result"] == "fix add"
    assert parent["secret"] == "no"


def test_stale_plan_does_not_edit() -> None:
    from core.kernel.plan import heartbeat_plan

    assert heartbeat_plan(stale=True, ollama=True)["next"] is None
    assert heartbeat_plan(stale=False, ollama=True)["next"] == "edit"


def test_memory_is_in_the_next_pack(tmp_path: Path) -> None:
    from core.kernel.edit_memory import remember

    remember(tmp_path, "changed add")
    (tmp_path / "add.py").write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
    text = pack(tmp_path, "add", ["add.py"], max_chars=500)
    assert "changed add" in text
    assert len(text) <= 500
