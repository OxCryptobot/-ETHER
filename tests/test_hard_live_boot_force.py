"""Ensure mutate tools are registered before scripted hard tests."""
from __future__ import annotations

from core.hard_live_boot import patch_runtime
from core.mutate_doctrine import apply
from core.tool_runtime import TOOL_SPECS, ToolRuntime


def test_force_boot_registers_mutate_tools():
    ToolRuntime._hard_live_booted = False  # type: ignore[attr-defined]
    patch_runtime()
    apply()
    names = {t["name"] for t in TOOL_SPECS}
    assert "edit_lines" in names
    assert "replace_once" in names
    assert "anchor_edit" in names or hasattr(ToolRuntime, "_obs_anchor_edit")
    assert hasattr(ToolRuntime, "_obs_replace_once")
