"""Every stage does real work."""
from __future__ import annotations

from pathlib import Path

from core.agent.gems import evolve, fabricate, memory, plan, profile, route, security


def test_plan_is_three_steps(tmp_path: Path) -> None:
    row = plan(tmp_path, "fix add")
    assert row["ok"] is True
    assert row["steps"] == ["search", "edit", "test"]


def test_route_sees_a_tool(tmp_path: Path) -> None:
    row = route(tmp_path, '{"tool": "search"}')
    assert row["kind"] == "tool"


def test_profile_needs_a_function(tmp_path: Path) -> None:
    assert profile(tmp_path, "def add(a, b):\n    return a + b")["shape"] is True
    assert profile(tmp_path, "I think")["shape"] is False


def test_security_rejects_a_shell(tmp_path: Path) -> None:
    assert security(tmp_path, "def bad():\n    import subprocess")["clean"] is False
    assert security(tmp_path, "def add(a, b):\n    return a + b")["clean"] is True


def test_evolve_skips_a_repeat(tmp_path: Path) -> None:
    memory(tmp_path, "tests passed")
    assert evolve(tmp_path, "tests passed")["new"] is False


def test_fabricate_knows_search(tmp_path: Path) -> None:
    assert fabricate(tmp_path, "search")["known"] is True
    assert fabricate(tmp_path, "nope")["known"] is False
