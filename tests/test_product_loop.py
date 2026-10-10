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
