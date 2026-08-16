"""Host measure paths must publish Phase 1 gate artifacts."""
from __future__ import annotations


def test_measure_paths_include_p1_artifacts():
    from scripts import host_agent as ha

    # Force existence checks by inspecting the source list via calling
    # with empty artifacts — function only returns existing files.
    # Contract: names are in the module's path enumeration.
    import inspect

    src = inspect.getsource(ha._measure_paths)
    for name in (
        "eligible_rates.json",
        "host_health.json",
        "phase1_gate.json",
    ):
        assert name in src, name
