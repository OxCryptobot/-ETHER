"""p3_57: stage annotation uses the typed gem registry."""
from core.loop.gem_step import annotate_stage


def test_tool_runtime_rose():
    a = annotate_stage("tool_runtime")
    assert a["gem"] == "rose_quartz"
    assert a["status"] == "partial"


def test_sandbox_live():
    a = annotate_stage("sandbox")
    assert a["gem"] == "clear_quartz"
    assert a["status"] == "live"


def test_unknown():
    a = annotate_stage("nope")
    assert a["gem"] is None
