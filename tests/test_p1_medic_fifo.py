"""p1 FAST: babysit medic jobs drain from FIFO; stand_down CLI."""
from __future__ import annotations

import inspect

from core.loop.medic import medic_stand_down
from scripts import host_agent as ha
from scripts import stand_down as sd


def test_list_pending_source_drains_babysit() -> None:
    src = inspect.getsource(ha.list_pending)
    assert "_is_babysit" in src
    assert "stood_down" in src


def test_stand_down_cli_go_without_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sd, "STATUS", tmp_path / "missing.json")
    assert sd.main() == 0


def test_stand_down_cli_skips_fresh_idle(tmp_path, monkeypatch) -> None:
    path = tmp_path / "status.json"
    path.write_text(
        '{"phase":"idle","heartbeat":"2099-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(sd, "STATUS", path)
    assert medic_stand_down(
        {"phase": "idle", "heartbeat": "2099-01-01T00:00:00+00:00"}
    )
    assert sd.main() == 78
