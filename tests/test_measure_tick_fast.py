"""FAST: slim measure tick exists and writes timestamp."""
from __future__ import annotations

from core.measure_tick_fast import run_fast


def test_run_fast_writes_stamp() -> None:
    out = run_fast()
    assert "timestamp" in out
    assert out.get("doctrine") == "measure_tick_fast"
    assert "honest_kpi" in (out.get("steps") or {})
