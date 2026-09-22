from gems.protocol import GEMS
from scripts.ether_evolve import cycle
from scripts.host_main import tick

def test_eight_gems_contract() -> None:
    assert len(GEMS) == 8
    roles = {g.role for g in GEMS}
    assert {"Planner", "Router", "Sandbox", "Memory", "Profiler", "Evolution", "Security", "Fabricate"} <= roles

def test_evolve_cycle_eight() -> None:
    row = cycle()
    assert row.get("ok") is True
    assert row.get("gems") == 8
    assert row["pillars"]["modular_intelligence"] is True
    assert row["pillars"]["controlled_evolution"] is True
    att = __import__("json").loads((__import__("pathlib").Path("artifacts/host_attach.json")).read_text(encoding="utf-8"))
    assert att.get("updated", "").startswith("2026-09-18") or att.get("clobber") is False

def test_host_main_observe_evolves() -> None:
    row = tick()
    assert row.get("note") == "observe_only"
    assert row.get("evolve", {}).get("gems") == 8
