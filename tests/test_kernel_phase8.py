"""Phase-8 extra tools, queue collapse, honest pipeline hook."""
from pathlib import Path
from core.kernel.extra_tools import apply_patch, dispatch, grep
from core.kernel.queue import collapse_legacy, queue_root
from core.pipeline_hooks import finalize_coding

class _RT:
    def __init__(self, ws: Path) -> None:
        self.workspace = ws
        self._edit_stack = []

def test_grep_and_unique_patch(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("x = 1\nx = 1\ndef add(a, b):\n    return a - b\n", encoding="utf-8")
    rt = _RT(tmp_path)
    assert grep(rt, "return a")["n"] >= 1
    out = apply_patch(rt, "mod.py", "return a - b", "return a + b")
    assert out["ok"] is True
    assert "return a + b" in src.read_text(encoding="utf-8")
    dup = apply_patch(rt, "mod.py", "x = 1", "x = 2")
    assert dup["ok"] is False and dup.get("error") == "old_not_unique"

def test_retry_is_parse_fail() -> None:
    row = dispatch(object(), "_retry", {"reason": "garbage"})
    assert row and row["error"] == "parse_fail" and row["ok"] is False

def test_queue_collapse(tmp_path: Path) -> None:
    legacy = tmp_path / "artifacts" / "pending"
    legacy.mkdir(parents=True)
    (legacy / "job.json").write_text("{}", encoding="utf-8")
    n = collapse_legacy(tmp_path)
    assert n == 1
    assert (queue_root(tmp_path) / "job.json").is_file()

def test_pipeline_hook_rejects_generate() -> None:
    row = finalize_coding({"ok": True, "tools": ["write_file"]}, path="generate")
    assert row["ok"] is False
