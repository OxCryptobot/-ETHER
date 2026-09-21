"""Phase-9 secret scan, hook timeout, rename/delete jail."""
from pathlib import Path
from core.kernel.extra_tools import apply_patch, delete, rename
from core.kernel.hooks import run_hook
from core.kernel.secret_scan import secret_hit

class _RT:
    def __init__(self, ws: Path) -> None:
        self.workspace = ws
        self._edit_stack = []

def test_secret_blocks_patch(tmp_path: Path) -> None:
    p = tmp_path / "a.py"
    p.write_text("x = 1\n", encoding="utf-8")
    assert secret_hit("api_key = 'sk-abcdefghijklmnop'") == "secret_in_write"
    row = apply_patch(_RT(tmp_path), "a.py", "x = 1", "token = 'ghp_abcdefghijklmnopqrstuv'")
    assert row["ok"] is False and row["error"] == "secret_in_write"

def test_rename_and_delete(tmp_path: Path) -> None:
    src = tmp_path / "old.py"
    src.write_text("ok\n", encoding="utf-8")
    rt = _RT(tmp_path)
    assert rename(rt, "old.py", "new.py")["ok"] is True
    assert (tmp_path / "new.py").is_file()
    assert delete(rt, "new.py")["ok"] is True
    assert not (tmp_path / "new.py").exists()

def test_hook_timeout() -> None:
    def boom() -> str:
        return "ok"
    assert run_hook(boom, timeout_s=1) == "ok"
    def hang() -> None:
        import time
        time.sleep(3)
    row = run_hook(hang, timeout_s=0.2)
    assert row["ok"] is False and row["error"] == "hook_timeout"
