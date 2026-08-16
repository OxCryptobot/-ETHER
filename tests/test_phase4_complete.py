"""Phase 4 advanced capability scaffolds."""
from __future__ import annotations


def test_toolkit_inventory():
    from core.phase4_toolkit import inventory

    out = inventory()
    assert out.get("ok") is True, out
    assert out.get("auto_promote") is False
    assert out.get("lib_ok") is True


def test_mcp_schema_offline():
    from core.phase4_mcp_schema import build_registry

    out = build_registry()
    assert out.get("ok") is True, out
    assert out.get("server_live") is False
    assert out.get("n_tools", 0) >= 5


def test_swarm_plan_only():
    from core.phase4_swarm_plan import plan

    out = plan("security audit and fix style", max_agents=3)
    assert out.get("ok") is True, out
    assert out.get("spawned") is False
    assert out.get("gpu") is False
    assert out.get("n_agents", 0) >= 1


def test_phase4_status():
    from core.phase4_status import compute

    out = compute()
    assert out.get("phase") == "4"
    assert out.get("soft_launch_blocked") is True
    assert out.get("training_wheels") is True
    assert len(out.get("locked") or []) >= 3
