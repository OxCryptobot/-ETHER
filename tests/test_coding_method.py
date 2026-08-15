"""Mentor coding_method contract must stay loadable and injectable."""
from __future__ import annotations


def test_coding_method_defaults():
    from core.coding_method import default_method, prompt_suffix, STEP_ORDER

    m = default_method()
    assert m.name == "ether_tool_first_v1"
    assert "run_tests" in STEP_ORDER
    assert "read tests" in m.checklist()
    block = prompt_suffix()
    assert "Coding method" in block or "ether_tool_first" in block
    assert "run_tests" in block


def test_tool_runtime_compiles_and_has_system_prompt():
    import ast
    from pathlib import Path

    src = Path("core/tool_runtime.py").read_text(encoding="utf-8")
    ast.parse(src)
    from core.tool_runtime import ToolRuntime, TOOL_SPECS

    assert hasattr(ToolRuntime, "_system_prompt")
    names = {t["name"] for t in TOOL_SPECS}
    assert "run_tests" in names
    # Doctrine import path present in source
    assert "coding_method" in src or "prompt_suffix" in src
