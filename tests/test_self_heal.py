from scripts.self_heal import arm

def test_self_heal_observe_only() -> None:
    row = arm()
    assert row.get("ok") is True
    assert row.get("note") == "observe_only" or row.get("os") == "nt"
