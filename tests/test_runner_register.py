"""Runner registration is observe-only off the 1650 and never stamps app_alive."""
import json
from pathlib import Path

from scripts.runner_register import register


def test_offbox_register_does_not_stamp_alive(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    before = (tmp_path / "artifacts" / "app_alive.json").exists()
    row = register()
    assert row.get("note") == "observe_only"
    assert row.get("alive_writer") == "1650_only"
    assert isinstance(row.get("runners"), int) or row.get("runners") is None
    assert "token" not in json.dumps(row)
    assert before is False
    assert not (tmp_path / "artifacts" / "app_alive.json").exists()


def test_offline_runner_is_not_counted_as_up() -> None:
    from scripts.runner_register import status_from_body
    state = status_from_body('{"total_count": 1, "runners": [{"name": "ETHER-1650", "status": "offline"}]}')
    assert state == {"total": 1, "online": 0}
    from scripts.runner_register import count_from_body
    assert count_from_body('{"total_count": 0}') == 0
    assert count_from_body("nope") is None


def test_worker_can_read_runners_and_rebase() -> None:
    text = Path(".github/workflows/matrix-worker.yml").read_text(encoding="utf-8")
    assert "administration:" not in text
    assert "git stash push -u -m worker-leftovers" in text
    assert "app_alive.json" not in text
