from scripts.ether_evolve import record, generation


def test_evolve_trace() -> None:
    p = record({"ok": True, "step": "unit"})
    assert p.is_file()
    assert generation() >= 1
