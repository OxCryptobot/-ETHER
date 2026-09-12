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


def test_schedule() -> None:
    from scripts.ether_cowork import schedule, due
    row = schedule("daily brief", 60)
    assert row["every_min"] == 60
    assert due() is True


def test_due_now() -> None:
    from scripts.ether_cowork import schedule, due_now, mark_ran
    schedule("brief", 60)
    assert due_now() is True
    mark_ran()
    assert due_now() is False


def test_set_folder(tmp_path) -> None:
    from scripts.ether_cowork import set_folder
    out = set_folder(str(tmp_path))
    assert out["ok"] is True
