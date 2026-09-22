from gems.protocol import GEMS
from scripts.ether_evolve import cycle
from scripts.host_main import tick
from pathlib import Path

def test_eight_gems_contract() -> None:
    assert len(GEMS) == 8
    roles = {g.role for g in GEMS}
    assert {"Planner", "Router", "Sandbox", "Memory", "Profiler", "Evolution", "Security", "Fabricate"} <= roles

def test_evolve_cycle_does_not_write_attach() -> None:
    p = Path("artifacts/host_attach.json")
    before = p.read_text(encoding="utf-8") if p.is_file() else ""
    row = cycle()
    after = p.read_text(encoding="utf-8") if p.is_file() else ""
    assert row.get("ok") is True
    assert row.get("gems") == 8
    assert row["pillars"]["modular_intelligence"] is True
    assert row["pillars"]["controlled_evolution"] is True
    assert before == after

def test_host_main_observe_evolves() -> None:
    row = tick()
    assert row.get("note") == "observe_only"
    assert row.get("evolve", {}).get("gems") == 8
