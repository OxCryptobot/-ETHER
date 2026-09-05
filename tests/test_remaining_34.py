"""Remaining-34 FAST: leftover modules import and fail-closed correctly."""
from __future__ import annotations

from core.loop.canned_tools import CANNED
from core.loop.fix_dag import fix_plan
from core.loop.flywheel import daily_scoreboard
from core.loop.living import FIXTURES, fabricate_stub
from core.loop.lsp import lsp_hover, lsp_status
from core.loop.moonshot import experimental_flags, lora_ready
from core.loop.resume import should_skip
from core.loop.worktree import add_worktree
from gems.grandidierite.fabricate import STUB_TEMPLATE, ast_validate, fabricate


def test_stub_named_entrypoint_no_notimplemented() -> None:
    assert "NotImplementedError" not in STUB_TEMPLATE
    assert "not implemented" not in STUB_TEMPLATE
    assert "def run_{name}" in STUB_TEMPLATE
    code = STUB_TEMPLATE.format(name="p3_75_echo", docstring="FAST stub")
    assert ast_validate(code)["ok"] is True
    assert "def run_p3_75_echo" in code


def test_p3_75_fabricate_stub() -> None:
    result = fabricate({"name": "p3_75_echo", "docstring": "FAST stub", "stub_only": True})
    assert result["name"] == "p3_75_echo"
    assert result.get("promoted") is False
    living = fabricate_stub("p3_75_living", purpose="living batch stub")
    assert living.get("promoted") is False


def test_lsp_fail_closed() -> None:
    st = lsp_status()
    assert st["ok"] is False
    assert st["error"] == "no_lsp_server"
    hv = lsp_hover("core/loop/living.py", 1, 0)
    assert hv["ok"] is False


def test_moonshot_lora_off_box() -> None:
    ready = lora_ready()
    assert ready["ok"] is False
    assert ready["reason"] == "off_box"
    flags = experimental_flags()
    assert flags["swarm"] is False
    assert flags["max_live_agents"] == 1


def test_pack_and_canned_and_dag() -> None:
    for name in ("merge", "ledger", "lru", "topo", "intervals"):
        assert name in FIXTURES
    assert len(CANNED) == 5
    plan = fix_plan("fix ledger")
    assert [s.action for s in plan.steps][:3] == ["observe", "mutate", "test"]
    board = daily_scoreboard([{"ok": True, "seconds": 1, "tools": ["run_tests"]}])
    assert board["ok"] == 1
    assert callable(add_worktree)
    assert should_skip("plan", None) is False
