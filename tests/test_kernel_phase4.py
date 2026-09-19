"""Phase-4 ToolRuntime constitution, permissions, loop guard."""
from core.kernel.constitution import TOOL_CONSTITUTION
from core.kernel.loop_guard import LoopGuard
from core.tool_runtime_kernel import check_tool, wrap_system_prompt

def test_constitution_injected() -> None:
    wrapped = wrap_system_prompt("You are a coding agent")
    assert "Never claim PASS" in wrapped
    assert wrapped.startswith(TOOL_CONSTITUTION.strip()[:20])
    again = wrap_system_prompt(wrapped)
    assert again.count("Never claim PASS") == 1

def test_shell_denied() -> None:
    row = check_tool("shell")
    assert row is not None and row["ok"] is False
    assert check_tool("read_file") is None
    assert check_tool("apply_patch") is None

def test_loop_guard_repeat_fail() -> None:
    g = LoopGuard(max_repeat=2)
    assert g.record("read_file", {"path": "a.py"}, ok=False)[0] is False
    assert g.record("read_file", {"path": "a.py"}, ok=False)[0] is True
