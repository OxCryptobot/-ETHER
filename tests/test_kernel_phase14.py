"""Phase-14 host_main observe-only off box."""
from scripts.host_main import tick

def test_host_main_observe_off_nt() -> None:
    row = tick()
    assert row["os"] != "nt" or row.get("pulse") is not None
    if row["os"] != "nt":
        assert row.get("note") == "observe_only"
