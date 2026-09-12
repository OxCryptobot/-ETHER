from scripts.ether_cowork import add, close, load


def test_cowork_board() -> None:
    row = add("wire local llm")
    assert row["status"] == "open"
    assert any(t["id"] == row["id"] for t in load())
    assert close(row["id"]) is True


def test_deliver() -> None:
    from scripts.ether_cowork import deliver
    out = deliver("brief", "local llm cowork")
    assert out["ok"] is True
    assert out["path"].endswith(".md")


def test_run_task() -> None:
    from scripts.ether_cowork import run_task
    out = run_task("live_host")
    assert out["ok"] is True
    assert out["deliverable"].endswith(".md")
