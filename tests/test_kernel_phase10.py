"""Phase-10 ignore, dirty-tree, memory schema."""
from pathlib import Path
from core.kernel.dirty import dirty
from core.kernel.ignore import ignored
from core.kernel.memory_schema import SCHEMA, accepted, stamp

def test_ignore_graveyard() -> None:
    assert ignored("scripts/_graveyard/old.py") is True
    assert ignored("core/kernel/ignore.py") is False

def test_memory_schema() -> None:
    row = stamp({"kind": "lesson"})
    assert row["schema"] == SCHEMA
    assert accepted(row) is True
    assert accepted({"kind": "lesson"}) is False

def test_dirty_handles_missing_git(tmp_path: Path) -> None:
    row = dirty(tmp_path)
    assert "dirty" in row
