"""p3_70: git tools in ToolRuntime; host skips babysit jobs when standing down."""
from pathlib import Path

from core.tool_runtime import TOOL_SPECS


def test_git_tools_in_specs():
    names = {t["name"] for t in TOOL_SPECS}
    assert "git_status" in names
    assert "git_diff" in names


def test_host_agent_stand_down_wired():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "host_agent.py").read_text(encoding="utf-8")
    assert "def _is_babysit" in src
    assert "stand-down skip babysit" in src
    assert "enqueue = klass not in" in src
