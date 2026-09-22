from scripts.ether_app import disk_tick, spawn_writer

def test_disk_tick_observe() -> None:
    row = disk_tick()
    assert row.get("ok") is True
    assert row.get("note") == "observe_only"

def test_spawn_writer_observe() -> None:
    row = spawn_writer()
    assert row.get("ok") is True
    assert row.get("note") == "observe_only"
