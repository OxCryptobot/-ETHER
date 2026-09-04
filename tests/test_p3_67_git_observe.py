"""p3_67: git observe tools are not mutate. MCP schema stays offline."""
from core.hard_live_tools import MUTATE_TOOLS, OBSERVE_TOOLS
from core.phase4_mcp_schema import _tool
from core.phase4_swarm_plan import plan
from core.loop.coord import MAX_LIVE_AGENTS


def test_git_is_observe_not_mutate():
    assert "git_status" in OBSERVE_TOOLS
    assert "git_diff" in OBSERVE_TOOLS
    assert "git_status" not in MUTATE_TOOLS
    assert "git_diff" not in MUTATE_TOOLS


def test_mcp_schema_helper_offline():
    spec = _tool("git_status", "porcelain status", {"cwd": {"type": "string"}}, [])
    assert spec["name"] == "git_status"
    assert "inputSchema" in spec or "parameters" in spec or spec.get("description")


def test_still_one_live_agent():
    payload = plan("git status")
    assert payload["spawned"] is False
    assert MAX_LIVE_AGENTS == 1
