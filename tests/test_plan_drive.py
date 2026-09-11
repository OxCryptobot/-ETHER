"""Planner must emit real ToolRuntime names, not JSON dump."""
from core.loop.plan_drive import planner_drives, tools_for_plan


def test_plan_emits_tool_order() -> None:
    tools = tools_for_plan("fix merge")
    assert tools[0] == "list_files"
    assert "run_tests" in tools
    assert "replace_once" in tools
    assert planner_drives("fix merge") is True
