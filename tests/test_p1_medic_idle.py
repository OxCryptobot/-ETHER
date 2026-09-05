"""p1 FAST: host_agent skips foreman/medic while idle with a fresh heartbeat."""
from __future__ import annotations

import inspect

from core.loop.medic import medic_stand_down
from scripts import host_agent as ha


def test_stand_down_on_fresh_idle() -> None:
    assert medic_stand_down({"phase": "idle", "heartbeat": "2099-01-01T00:00:00+00:00"}) is True


def test_stand_up_when_stale() -> None:
    assert medic_stand_down({"phase": "idle", "heartbeat": "2000-01-01T00:00:00+00:00"}) is False


def test_host_agent_guards_foreman() -> None:
    src = inspect.getsource(ha)
    assert "medic_stand_down" in src
    assert "_foreman_allowed" in src
