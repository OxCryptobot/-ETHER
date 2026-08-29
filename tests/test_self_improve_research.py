"""Research + versions + dual-window protocol."""
from __future__ import annotations

from pathlib import Path

from core.mutate_doctrine import suffix
from core.self_improve_research import research
from core.self_improve_versions import rollback, snapshot


def test_research_returns_corpus():
    out = research("hard_live")
    assert "lessons" in out
    assert "external" in out
    assert "escalate_grok" in str(out.get("external"))


def test_snapshot_and_rollback(tmp_path: Path):
    src = tmp_path / "p.json"
    src.write_text('{"v": 1}', encoding="utf-8")
    dest = snapshot("imp_test", src)
    assert dest is not None and dest.exists()
    src.write_text('{"v": 2}', encoding="utf-8")
    rb = rollback("imp_test", src)
    assert rb.get("ok") is True
    assert '"v": 1' in src.read_text(encoding="utf-8")


def test_doctrine_names_anchor_edit():
    text = suffix()
    assert "anchor_edit" in text
    assert "write_file" in text
