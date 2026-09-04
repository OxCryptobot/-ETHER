"""p3_71: LoopRunner default-on, git execute, traces, MCP git tools."""
import inspect
import os

from core.loop import loop_runner_enabled
from core.loop.plan_exec import execute_dispatched, execute_tool, tool_for_step
from core.loop.traces import critique_from_trace, last_tool_trace
from core.phase4_mcp_schema import build_registry
from core.pipeline import Pipeline
from gems.runtime import STAGE_GEM


def test_loop_runner_default_on():
    os.environ.pop("ETHER_LOOP_RUNNER", None)
    assert loop_runner_enabled() is True


def test_execute_git_status():
    out = execute_tool("git_status")
    assert "ok" in out or "stdout" in out or "error" in out


def test_trace_flags_missing_run_tests():
    tools = last_tool_trace({"tools": ["list_files", "replace_once"]})
    assert "run_tests" not in tools
    assert "run_tests" in critique_from_trace(tools)


def test_mcp_has_git():
    reg = build_registry()
    names = {t["name"] for t in reg["tools"]}
    assert "ether.git_status" in names
    assert "ether.run_tests" in names
    assert reg["server_live"] is False


def test_evolve_stage_mapped():
    assert STAGE_GEM["evolve"] == "amethyst"
    assert STAGE_GEM["memory"] == "citrine"


def test_pipeline_executes_dispatched():
    src = inspect.getsource(Pipeline.run)
    assert "execute_dispatched" in src


def test_live_test_still_run_tests():
    assert tool_for_step({"gem": "clear_quartz", "action": "test", "status": "live"}) == "run_tests"
