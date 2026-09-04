"""p4_01 FAST: fix-task DAG observe → mutate → run_tests → validate."""
from __future__ import annotations

from core.loop.fix_dag import execute_fix, fix_plan, tool_order, walk_fix
from core.loop.plan_walk import topo_sort


def test_fix_plan_order() -> None:
    order = [s.id for s in topo_sort(fix_plan("ledger"))]
    assert order == [1, 2, 3, 4]


def test_mutate_before_run_tests() -> None:
    rows = walk_fix("merge")
    tools = tool_order(rows)
    assert "replace_once" in tools
    assert "run_tests" in tools
    assert tools.index("replace_once") < tools.index("run_tests")


def test_observe_is_first() -> None:
    rows = walk_fix()
    assert rows[0]["action"] == "observe"
    assert rows[0]["tool"] == "list_files"


def test_validate_last_maps_security() -> None:
    rows = walk_fix()
    assert rows[-1]["action"] == "validate"
    assert rows[-1]["gem"] == "black_tourmaline"


def test_execute_fix_does_not_crash() -> None:
    out = execute_fix("phase4")
    assert out["ok"] is True
    assert out["n"] == 4
    assert out["tools"][0] == "list_files"
