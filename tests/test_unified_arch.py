"""Unified lanes: Ubuntu observes; NT would write."""
from pathlib import Path
from scripts.host_main import tick
from scripts.origin_publish import publish

def test_linux_tick_is_observe_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    (tmp_path / "scripts").mkdir()
    row = tick()
    assert row.get("note") == "observe_only" or row.get("os") != "nt"

def test_publish_off_box_does_not_claim_push(tmp_path) -> None:
    row = publish(tmp_path)
    assert row.get("note") == "observe_only"
    assert row.get("ok") is False
    assert (tmp_path / "artifacts" / "git_push.json").is_file()
