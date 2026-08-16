"""GEM energy strip contracts."""
from __future__ import annotations

from core.gem_energy import infer_gem, publish


def test_infer_labradorite():
    assert infer_gem("critique_on_fail plan_wire") == "labradorite"


def test_infer_clear_quartz():
    assert infer_gem("ss_tool_runtime pytest") == "clear-quartz"


def test_infer_rose():
    assert infer_gem("ss_pipeline_scripted") == "rose-quartz"


def test_publish():
    p = publish()
    assert "last_gem" in p or p.get("last_gem") is None
    assert "strip" in p
    assert len(p["strip"]) == 8
    assert p.get("path")
