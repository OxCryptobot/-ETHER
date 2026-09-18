"""Phase-1 kernel contracts. Fast, no model, no GPU."""
from __future__ import annotations
import os
from pathlib import Path
from core.kernel.honest import is_honest_tool_path_pass, reject_generate_pass
from core.kernel.writer import allow_attach_write, liveness
from core.kernel.job_schema import validate_job
from core.kernel.plan import Node, PlanGraph
from core.kernel.loop_guard import LoopGuard
from core.kernel.edit_tx import EditTx
from core.kernel.constitution import TOOL_CONSTITUTION
from core.kernel.context_budget import context_char_budget

def test_generate_is_never_honest_pass() -> None:
    assert is_honest_tool_path_pass({"ok": True, "strategy": "generate", "mode": "live"}) is False
    assert is_honest_tool_path_pass({"ok": True, "generate_fallback": True}) is False
    row = reject_generate_pass({"ok": True, "strategy": "best_of_n"})
    assert row["ok"] is False and row["honest"] is False

def test_tool_path_can_pass() -> None:
    row = {"ok": True, "tool_runtime_ok": True, "tests_ok": True, "steps": [{"tool": "run_tests"}], "strategy": "tool_runtime"}
    assert is_honest_tool_path_pass(row) is True

def test_job_schema() -> None:
    ok, err = validate_job({"id": "p1_a", "class": "fast", "steps": [{"argv": ["pytest"], "timeout": 30}]})
    assert ok and not err
    bad, errs = validate_job({"id": "../x", "steps": []})
    assert bad is False

def test_plan_fast_before_live() -> None:
    g = PlanGraph(goal="fix")
    g.add(Node(id="a", goal="tests", class_="fast", confidence=0.9))
    g.add(Node(id="b", goal="live", class_="live", depends_on=["a"], confidence=0.9))
    first = g.next_live()
    assert first is not None and first.id == "a"
    g.resolve("a", True)
    second = g.next_live()
    assert second is not None and second.id == "b"

def test_loop_guard_repeats() -> None:
    g = LoopGuard(max_repeat=2)
    stop, _ = g.record("read_file", {"path": "a.py"}, False)
    assert stop is False
    stop, reason = g.record("read_file", {"path": "a.py"}, False)
    assert stop is True and reason == "no_progress_repeat"

def test_edit_tx(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "f.txt").write_text("one", encoding="utf-8")
    tx = EditTx(ws, tmp_path / "snap")
    tx.begin()
    (ws / "f.txt").write_text("two", encoding="utf-8")
    tx.finish(False)
    assert (ws / "f.txt").read_text(encoding="utf-8") == "one"

def test_constitution_present() -> None:
    assert "Matrix is a dashboard" in TOOL_CONSTITUTION

def test_context_budget() -> None:
    assert 800 <= context_char_budget(8192) <= 8000

def test_ubuntu_cannot_clobber_attach() -> None:
    if os.name == "nt":
        assert allow_attach_write(ollama_up=True) is True
    else:
        assert allow_attach_write(ollama_up=False, writer_claim="exe") is False
        assert allow_attach_write(ollama_up=True) is False

def test_liveness_triple() -> None:
    row = liveness(proc_alive=True, ollama_up=False, drain_alive=False)
    assert row["proc"] is True and row["ollama"] is False
