"""Pure terminal + burst — no Pipeline.run."""
from __future__ import annotations

import os


def test_terminal_fail_tool_runtime():
    from core.pipeline_terminal import decide_terminal

    out = decide_terminal(
        tool_runtime_enabled=True,
        tool_runtime_done=False,
        score=0.2,
        degraded=["x"],
    )
    assert out["ok"] is False
    assert out["should_fail"] is True
    assert out["marker"] == "tool_runtime_failed_terminal"
    assert "tool_runtime_failed_terminal" in out["degraded"]
    assert "x" in out["degraded"]


def test_terminal_ok_when_done():
    from core.pipeline_terminal import decide_terminal

    out = decide_terminal(tool_runtime_enabled=True, tool_runtime_done=True, score=0.95)
    assert out["ok"] is True
    assert out["should_fail"] is False
    assert out["score"] == 0.95


def test_burst_disabled_by_default():
    from core.burst_policy import burst_enabled, should_force_burst

    # default env: off
    os.environ.pop("ETHER_BURST", None)
    os.environ.pop("ETHER_FORCE_BURST", None)
    assert burst_enabled() is False
    assert should_force_burst(attempt=3, strategy="default", multifile=True) is False


def test_burst_on_fail_when_enabled(monkeypatch=None):
    from core import burst_policy as bp

    old = os.environ.get("ETHER_BURST")
    try:
        os.environ["ETHER_BURST"] = "1"
        assert bp.burst_enabled() is True
        assert bp.should_force_burst(attempt=2, strategy="default") is True
        assert bp.should_force_burst(attempt=1, strategy="default") is False
        assert bp.should_force_burst(attempt=1, hard_tag=True) is True
    finally:
        if old is None:
            os.environ.pop("ETHER_BURST", None)
        else:
            os.environ["ETHER_BURST"] = old


def test_pipeline_burst_adapter():
    from core.pipeline_burst import decide_burst

    # burst off → False
    os.environ.pop("ETHER_BURST", None)
    assert decide_burst(2, "default", "refactor module") is False


def test_shadow_tag_runs():
    from core.shadow_tag import compute

    out = compute()
    assert "n_tags" in out
    assert out.get("path")
