"""FAST tests for audit findings F05–F13. No inspect.getsource on Pipeline.run."""
from __future__ import annotations

from core.ast_transaction import EditTransaction
from core.context import compress_text
from core.gem_energy import GEMS, bump
from core.loop.job_argv import argv_ok
from core.loop.live_criteria import unaided_pass


def test_f03_craft_helper_is_not_unaided() -> None:
    assert unaided_pass({"policy": "craft_helper", "ok": True, "score": 1.0, "tools": ["bug_comments", "replace_once", "run_tests"]}) is False
    assert unaided_pass({"policy": "model", "ok": True, "score": 1.0, "tools": ["bug_comments", "replace_once", "run_tests"]}) is True


def test_f05_bump_named_gem() -> None:
    out = bump("citrine", job="findings_batch")
    assert out["wired"] is True
    assert out["counts"]["citrine"] >= 1
    assert set(GEMS) == set(out["counts"])


def test_f07_compress_truncates() -> None:
    blob = ("def foo():\n    return 1\n\n" * 400) + "\nquery term pipeline tool_runtime\n"
    out = compress_text(blob, query="pipeline tool_runtime", max_chars=800)
    assert len(out) <= 800
    assert out


def test_f09_lora_is_prompt_adapter() -> None:
    from pathlib import Path
    import json
    import os
    root = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1])
    p = root / "artifacts" / "lora" / "adapter.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("kind") == "prompt_adapter"
    assert data.get("peft") is False


def test_f13_argv_allowlist() -> None:
    assert argv_ok([".venv/Scripts/python.exe", "-m", "pytest", "tests/test_live_criteria.py"])
    assert argv_ok(["python", "-m", "core.measure_tick"]) is True
    assert argv_ok(["powershell", "Remove-Item", "C:\\"]) is False
    assert argv_ok([".venv/Scripts/python.exe", "-c", "import os; os.system('rm -rf /')"]) is False


def test_f06_ast_transaction_on_merge_snippet() -> None:
    src = "def merge(a, b):\n    return a\n"
    bad = "def merge(a, b)\n    return a\n"
    tx = EditTransaction(allow_outside_root=True, require_ast=True)
    raised = False
    try:
        tx.write("/tmp/ether_ast_merge.py", bad)
    except ValueError:
        raised = True
    assert raised
    tx2 = EditTransaction(allow_outside_root=True, require_ast=True)
    tx2.write("/tmp/ether_ast_merge.py", src)
    assert "ether_ast_merge.py" in "".join(tx2.pending_paths)
