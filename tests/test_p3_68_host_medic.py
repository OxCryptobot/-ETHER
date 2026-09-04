"""p3_68: host_health reports medic_stand_down from the idle lock."""
import inspect
from core.host_health import compute


def test_compute_has_medic_flag():
    src = inspect.getsource(compute)
    assert "medic_stand_down" in src
    payload = compute()
    assert "medic_stand_down" in payload
