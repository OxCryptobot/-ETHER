"""Phase 2.2 — multi-file AST transactional writes."""
from __future__ import annotations

from pathlib import Path

from core.ast_transaction import EditTransaction, transactional_write_many
from core.multifile import extract_file_blocks, write_pair


def test_extract_file_blocks():
    src = (
        "# file: util.py\n"
        "def add(a, b):\n    return a + b\n"
        "# file: main.py\n"
        "from util import add\nassert add(1, 2) == 3\n"
    )
    files = extract_file_blocks(src)
    assert "util.py" in files and "main.py" in files


def test_write_pair_ast_reject_does_not_partial_write(tmp_path, monkeypatch):
    monkeypatch.setattr("core.multifile.SCRATCH", tmp_path)
    monkeypatch.setattr("core.multifile.ROOT", tmp_path)
    bad = {
        "ok.py": "def ok():\n    return 1\n",
        "bad.py": "def broken(:\n    pass\n",
    }
    result = write_pair(bad)
    assert result.get("ok") is False
    assert not (tmp_path / "ok.py").exists()
    assert not (tmp_path / "bad.py").exists()


def test_write_pair_two_files_ok(tmp_path, monkeypatch):
    monkeypatch.setattr("core.multifile.SCRATCH", tmp_path)
    monkeypatch.setattr("core.multifile.ROOT", tmp_path)
    good = {
        "util.py": "def add(a, b):\n    return a + b\n",
        "main.py": "from util import add\nassert add(2, 3) == 5\n",
    }
    result = write_pair(good)
    assert result.get("ok") is True
    assert (tmp_path / "util.py").is_file()
    assert (tmp_path / "main.py").is_file()
    assert result.get("ast_gated") is True


def test_apply_many_rollback_on_verify_fail(tmp_path):
    root = tmp_path
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    with EditTransaction(root) as tx:
        tx.apply_many({"a.py": "x = 2\n", "b.py": "y = 3\n"})
        result = tx.verify_and_commit(lambda: False)
    assert result.ok is False
    assert result.rolled_back is True
    assert (root / "a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert not (root / "b.py").exists()


def test_transactional_write_many_success(tmp_path):
    result = transactional_write_many(
        {"u.py": "def f():\n    return 1\n", "v.py": "from u import f\nassert f() == 1\n"},
        verify=lambda: True,
        root=tmp_path,
    )
    assert result.ok is True
    assert result.committed is True
    assert (tmp_path / "u.py").is_file()
