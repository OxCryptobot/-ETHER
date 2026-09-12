from scripts.ether_role import tick, ROLE


def test_self_build_role() -> None:
    row = tick()
    assert row["role"] == ROLE
    assert row["ok"] is True
    assert str(row.get("plan") or "").endswith(".md")
