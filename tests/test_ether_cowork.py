from scripts.ether_cowork import add, close, load


def test_cowork_board() -> None:
    row = add("wire local llm")
    assert row["status"] == "open"
    assert any(t["id"] == row["id"] for t in load())
    assert close(row["id"]) is True
