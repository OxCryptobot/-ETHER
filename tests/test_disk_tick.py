from scripts.ether_app import disk_tick

def test_disk_tick_observe() -> None:
    row = disk_tick()
    assert row.get("ok") is True
    assert row.get("note") == "observe_only"
