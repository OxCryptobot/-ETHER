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


def test_startup_vbs_is_real_script() -> None:
    from pathlib import Path
    from scripts.self_heal import keepalive_vbs
    text = keepalive_vbs(
        Path(r"C:\Users\Otcde\ETHER\.venv\Scripts\pythonw.exe"),
        Path(r"C:\Users\Otcde\ETHER\scripts\ether_keepalive.py"),
    )
    lines = text.splitlines()
    assert len(lines) == 2
    assert lines[0] == 'Set s=CreateObject("WScript.Shell")'
    assert lines[1].startswith("s.Run ")
    assert "\\n" not in text
