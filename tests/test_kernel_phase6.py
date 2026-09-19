"""Phase-6 symbol index, sandbox, deadline, targeted tests, contract."""
from pathlib import Path
from core.kernel.cancel import Deadline
from core.kernel.contract import inject
from core.kernel.index import build_index, format_hits, query_index
from core.kernel.progress import snapshot
from core.kernel.sandbox import allowed, resolve_in
from core.kernel.select_tests import pytest_argv, select_from_fail

def test_index_finds_kernel_symbols(tmp_path: Path) -> None:
    src = tmp_path / "core"
    src.mkdir()
    (src / "demo.py").write_text("def alpha_target():\n    return 1\n\nclass Bravo:\n    pass\n", encoding="utf-8")
    idx = build_index(tmp_path)
    hits = query_index(idx, "alpha_target Bravo")
    assert hits and "demo.py" in format_hits(hits)

def test_sandbox_blocks_escape(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x=1\n", encoding="utf-8")
    assert allowed(tmp_path, "ok.py") is True
    assert allowed(tmp_path, "../secret") is False
    assert allowed(tmp_path, "/etc/passwd") is False
    resolve_in(tmp_path, "ok.py")

def test_deadline_and_selector() -> None:
    assert Deadline(2).expired() is False
    assert select_from_fail("FAILED tests/test_kernel_phase6.py::test_x") == ["tests/test_kernel_phase6.py::test_x"]
    assert "-q" in pytest_argv(["tests/test_kernel_phase6.py"])

def test_contract_and_progress(tmp_path: Path) -> None:
    (tmp_path / "ETHER.md").write_text("# ETHER\nMatrix is read-only.\n", encoding="utf-8")
    text = inject(tmp_path)
    assert "Never claim PASS" in text or "Matrix is read-only" in text
    snap = snapshot()
    assert snap["soft_launch"] == "blocked"
    assert snap["kernel_contracts_pct"] >= 50
