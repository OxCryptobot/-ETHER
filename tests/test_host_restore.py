from scripts.start_runner import start_runner
from scripts.host_main import tick

def test_start_runner_observe_off_nt() -> None:
    row = start_runner()
    assert row.get("note") == "observe_only" or row.get("ok") is True

def test_host_main_tick_writes_row() -> None:
    row = tick()
    assert "ts" in row
    assert row.get("os") != "nt" or "runner" in row or "runner_error" in row
