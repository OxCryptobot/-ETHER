"""p3_56: LoopRunner dispatches stages through the typed gem registry."""
from core.loop.runner import LoopRunner


def test_tool_runtime_is_rose():
    runner = LoopRunner(registry=object())
    gem = runner.gem_for("tool_runtime")
    assert gem is not None
    assert gem.id == "rose_quartz"


def test_sandbox_live():
    runner = LoopRunner(registry=object())
    gem = runner.gem_for("sandbox")
    assert gem is not None
    assert gem.id == "clear_quartz"
    assert gem.status == "live"


def test_tool_first_walk():
    runner = LoopRunner(registry=object())
    gems = runner.tool_first_gems()
    ids = [g.id for g in gems]
    assert "rose_quartz" in ids
    assert "clear_quartz" in ids
    assert "selenite" in ids


def test_unknown_none():
    runner = LoopRunner(registry=object())
    assert runner.gem_for("nope") is None
