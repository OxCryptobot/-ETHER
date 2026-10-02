"""The product path keeps an edit only when tests pass, and generate is not honest."""
from pathlib import Path

from core.kernel.context_budget import pack
from core.kernel.product_loop import run_edit, run_model_edit
from core.kernel.subagent import isolate


def test_generate_text_is_not_a_pass(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "add.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    row = run_model_edit(ws, "add.py", "def add(a, b):\n    return a + b\n", lambda: True)
    assert row["honest"] is False
    assert row["strategy"] == "generate"
    assert "return a - b" in (ws / "add.py").read_text(encoding="utf-8")


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
