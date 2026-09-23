"""Keepalive is one host_main pass. Off the 1650 it must not fake alive."""
from scripts.ether_keepalive import tick


def test_keepalive_tick_does_not_fake_live() -> None:
    out = tick()
    assert isinstance(out, dict)
    assert out.get("os") in {"posix", "nt"}
    if out.get("os") != "nt":
        assert out.get("note") == "observe_only"
        assert out.get("alive") is None
        pillars = (out.get("evolve") or {}).get("pillars") or {}
        assert pillars.get("modular_intelligence") is True
        assert pillars.get("verified_execution") is True
