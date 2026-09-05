"""Leftover FAST gate: single-consumer lock + leftover modules import."""
from __future__ import annotations

from core.loop.coord import MAX_LIVE_AGENTS, SPAWNED, assert_single_consumer
from core.loop.lsp import lsp_status
from core.loop.moonshot import experimental_flags
from core.model_router import select_backend
from scripts.deploy_pipeline import GATES
from scripts.pep8_loop import SCOPE


def test_single_consumer() -> None:
    assert MAX_LIVE_AGENTS == 1
    assert SPAWNED is False
    assert_single_consumer({"spawned": False, "agents": []})


def test_gates_cover_leftovers() -> None:
    joined = " ".join(GATES)
    assert "test_scale_plane.py" in joined
    assert "test_remaining_34.py" in joined
    assert "test_p3_75" in joined
    assert "core/model_router.py" in SCOPE


def test_scale_and_lsp_fail_closed_defaults() -> None:
    st = lsp_status()
    assert st["ok"] is False
    flags = experimental_flags()
    assert flags["swarm"] is False
    b = select_backend("fast")
    assert b["backend"] == "ollama"
    assert b["lane"] == "fast"
