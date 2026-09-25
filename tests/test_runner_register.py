"""Runner registration is observe-only off the 1650 and never stamps app_alive."""
import json

from scripts.runner_register import register


def test_offbox_register_does_not_stamp_alive(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    before = (tmp_path / "artifacts" / "app_alive.json").exists()
    row = register()
    assert row.get("note") == "observe_only"
    assert row.get("alive_writer") == "1650_only"
    assert row.get("runners") in {0, None}
    assert "token" not in json.dumps(row)
    assert before is False
    assert not (tmp_path / "artifacts" / "app_alive.json").exists()
