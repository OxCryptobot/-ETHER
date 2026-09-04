"""p3_55: gem dispatch maps live stages to the typed registry."""
from gems.runtime import STAGE_GEM, gem_for_stage


def test_tool_runtime_is_rose():
    g = gem_for_stage("tool_runtime")
    assert g is not None
    assert g.id == "rose_quartz"


def test_sandbox_is_clear_and_live():
    g = gem_for_stage("sandbox")
    assert g is not None
    assert g.id == "clear_quartz"
    assert g.status == "live"


def test_unknown_stage_none():
    assert gem_for_stage("nope") is None


def test_all_mapped_exist():
    for stage, gid in STAGE_GEM.items():
        g = gem_for_stage(stage)
        assert g is not None, stage
        assert g.id == gid
