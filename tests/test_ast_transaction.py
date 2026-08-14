"""Package 1C — AST transactional edits."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from core.ast_transaction import EditTransaction, transactional_write


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path


def test_write_and_commit(tmp_root: Path) -> None:
    target = tmp_root / "mod.py"
    src = "def add(a, b):\n    return a + b\n"
    with EditTransaction(tmp_root) as tx:
        tx.write("mod.py", src)
        result = tx.commit()
    assert result.ok and result.committed
    assert target.read_text(encoding="utf-8") == src


def test_ast_reject_syntax_error(tmp_root: Path) -> None:
    bad = "def broken(:\n    pass\n"
    with EditTransaction(tmp_root) as tx:
        with pytest.raises(ValueError, match="AST reject"):
            tx.write("bad.py", bad)


def test_rollback_on_verify_fail(tmp_root: Path) -> None:
    original = "x = 1\n"
    target = tmp_root / "state.py"
    target.write_text(original, encoding="utf-8")

    with EditTransaction(tmp_root) as tx:
        tx.write("state.py", "x = 99\n")
        result = tx.verify_and_commit(lambda: False)

    assert not result.ok
    assert result.rolled_back
    assert target.read_text(encoding="utf-8") == original


def test_commit_on_verify_pass(tmp_root: Path) -> None:
    target = tmp_root / "ok.py"
    new = "y = 2\n"
    with EditTransaction(tmp_root) as tx:
        tx.write("ok.py", new)
        result = tx.verify_and_commit(lambda: True)
    assert result.ok and result.committed
    assert target.read_text(encoding="utf-8") == new


def test_path_escape_rejected(tmp_root: Path) -> None:
    with EditTransaction(tmp_root) as tx:
        with pytest.raises(ValueError, match="escape"):
            tx.write("../outside.py", "x = 1\n")


def test_multi_file_atomic_rollback(tmp_root: Path) -> None:
    a = tmp_root / "a.py"
    b = tmp_root / "b.py"
    a.write_text("A = 1\n", encoding="utf-8")
    b.write_text("B = 1\n", encoding="utf-8")

    with EditTransaction(tmp_root) as tx:
        tx.write("a.py", "A = 9\n")
        tx.write("b.py", "B = 9\n")
        result = tx.verify_and_commit(lambda: False)

    assert result.rolled_back
    assert a.read_text(encoding="utf-8") == "A = 1\n"
    assert b.read_text(encoding="utf-8") == "B = 1\n"


def test_new_file_removed_on_rollback(tmp_root: Path) -> None:
    target = tmp_root / "brand_new.py"
    assert not target.exists()
    with EditTransaction(tmp_root) as tx:
        tx.write("brand_new.py", "z = 0\n")
        result = tx.verify_and_commit(lambda: False)
    assert result.rolled_back
    assert not target.exists()


def test_helper_transactional_write(tmp_root: Path) -> None:
    result = transactional_write(
        "helper.py",
        "def f():\n    return 42\n",
        lambda: True,
        root=tmp_root,
    )
    assert result.ok
    assert (tmp_root / "helper.py").exists()


def test_context_manager_auto_rollback_on_exception(tmp_root: Path) -> None:
    target = tmp_root / "auto.py"
    target.write_text("old\n", encoding="utf-8")
    try:
        with EditTransaction(tmp_root) as tx:
            tx.write("auto.py", "new\n")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert target.read_text(encoding="utf-8") == "old\n"
