"""Daemon publish uses host_main and does not stamp LIVE off the 1650."""
from scripts.ether_daemon import publish_host


def test_publish_host_observe_only_off_box() -> None:
    row = publish_host()
    assert isinstance(row, dict)
    if row.get("os") != "nt":
        assert row.get("note") == "observe_only"
        assert row.get("alive") is None
        assert (row.get("evolve") or {}).get("walk_ok") is True
