"""Phase 2.4 — symbol/file index must not change default pipeline paths."""
from __future__ import annotations

import os
from pathlib import Path

from core.symbol_index import (
    extract_symbols,
    format_block,
    index_tree,
    rank,
    search,
    symbol_index_enabled,
)


def test_extract_symbols_defs_and_classes():
    src = (
        "class Foo:\n"
        "    def bar(self):\n"
        "        return 1\n"
        "def baz():\n"
        "    return 2\n"
    )
    names = extract_symbols(src)
    assert "Foo" in names
    assert "Foo.bar" in names
    assert "baz" in names


def test_extract_symbols_bad_syntax_returns_empty():
    assert extract_symbols("def broken(:\n    pass\n") == []


def test_index_and_rank_prefers_matching_path(tmp_path: Path):
    (tmp_path / "ledger.py").write_text(
        "def balance():\n    return 0\n", encoding="utf-8"
    )
    (tmp_path / "unrelated.py").write_text(
        "def hello():\n    return 'hi'\n", encoding="utf-8"
    )
    entries = index_tree(tmp_path)
    hits = rank(entries, "ledger balance", k=5)
    assert hits
    assert hits[0][1].path.endswith("ledger.py")


def test_format_block_respects_budget(tmp_path: Path):
    for i in range(20):
        (tmp_path / f"mod_{i}.py").write_text(
            f"def func_{i}():\n    return {i}\n", encoding="utf-8"
        )
    block = format_block("func_3", root=tmp_path, k=10, max_chars=200)
    assert len(block) <= 200
    assert "func_3" in block or "mod_3" in block


def test_search_structured(tmp_path: Path):
    (tmp_path / "gate.py").write_text(
        "def is_honest_tool_path_pass():\n    return True\n", encoding="utf-8"
    )
    rows = search("honest tool path", root=tmp_path, k=3)
    assert isinstance(rows, list)
    assert rows[0]["path"].endswith("gate.py")


def test_symbol_index_default_off():
    prev = os.environ.pop("ETHER_SYMBOL_INDEX", None)
    try:
        assert symbol_index_enabled() is False
    finally:
        if prev is not None:
            os.environ["ETHER_SYMBOL_INDEX"] = prev


def test_pipeline_still_imports_after_index():
    from core.pipeline import Pipeline

    assert Pipeline is not None
