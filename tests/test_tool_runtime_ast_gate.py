"""Package 1C — AST gate on tool_runtime write_file."""
from __future__ import annotations

from pathlib import Path

from core.tool_runtime import ToolRuntime, _ast_reject_py


def test_ast_reject_helper() -> None:
    assert _ast_reject_py("ok.py", "x = 1\n") is None
    err = _ast_reject_py("bad.py", "def broken(:\n    pass\n")
    assert err is not None and "AST reject" in err
    assert _ast_reject_py("notes.txt", "not python {") is None


def test_write_file_rejects_bad_python(tmp_path: Path) -> None:
    # Minimal fixture layout
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_noop.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "pkg.py").write_text("x = 1\n", encoding="utf-8")

    def decide(_msgs):
        return {"tool": "done", "args": {"reason": "stop"}}

    rt = ToolRuntime(fixture_root=tmp_path, decide_fn=decide, max_steps=2)
    rt.workspace = tmp_path  # bypass seed for unit test
    obs = rt._obs_write("pkg.py", "def broken(:\n    pass\n")
    assert obs.get("ok") is False
    assert "AST reject" in str(obs.get("error") or "")
    # original content untouched
    assert (tmp_path / "pkg.py").read_text(encoding="utf-8") == "x = 1\n"


def test_write_file_accepts_valid_python(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_noop.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "pkg.py").write_text("x = 1\n", encoding="utf-8")

    def decide(_msgs):
        return {"tool": "done", "args": {"reason": "stop"}}

    rt = ToolRuntime(fixture_root=tmp_path, decide_fn=decide, max_steps=2)
    rt.workspace = tmp_path
    obs = rt._obs_write("pkg.py", "x = 42\n")
    assert obs.get("ok") is True
    assert (tmp_path / "pkg.py").read_text(encoding="utf-8") == "x = 42\n"
