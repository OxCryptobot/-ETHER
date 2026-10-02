"""The heartbeat publishes. It does not call the model or treat generate as a pass."""
from pathlib import Path

from core.agent_loop import LoopResult


def test_windows_tick_stops_before_the_model() -> None:
    body = Path("scripts/host_main.py").read_text(encoding="utf-8").split("def tick", 1)[1]
    nt, _, observe = body.partition("from scripts.ether_evolve import cycle")
    assert observe
    assert "ether_evolve" not in nt
    assert "ether_role" not in body
    assert "drain_live_fifo" in nt
    assert body.index("mark_alive") < body.index("_pull(")


def test_generate_loop_is_not_an_honest_pass() -> None:
    row = LoopResult(objective="add").to_dict()
    assert row["strategy"] == "generate"
    assert row["honest"] is False


def test_edit_job_does_not_exec_the_reply() -> None:
    text = Path("scripts/live_edit_tx.py").read_text(encoding="utf-8")
    assert "exec(" not in text
    assert "function_ok" in text


def test_runner_service_is_not_started_off_windows() -> None:
    from scripts.runner_service import ensure_service
    assert ensure_service()["note"] == "observe_only"
