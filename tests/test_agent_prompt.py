from core.kernel.agent_prompt import SYSTEM, messages


def test_the_prompt_fits_a_4b_and_speaks_the_parser() -> None:
    assert len(SYSTEM) < 500
    assert "READ:" in SYSTEM
    assert "complete function" in SYSTEM
    for leaked in ("return a + b", "s[0] + s[-1]", "return 'ada'", "hi ada"):
        assert leaked not in SYSTEM
    sent = messages("Failing cases:\nends")
    assert sent[0]["role"] == "system"
    assert sent[1] == {"role": "user", "content": "Failing cases:\nends"}


def test_the_edit_turn_stops_asking_for_read() -> None:
    from core.kernel.curriculum import TASKS
    from core.kernel.read_gate import blind_prompt, for_edit, repair_ask

    task = next(item for item in TASKS if item["id"] == "ends")
    shown = blind_prompt(task, "ends(ether) returned e, expected er")
    shown += "\n\n### ends.py\n" + task["source"]
    edit = for_edit(shown, task["prompt"], [])
    assert "READ:" not in edit
    assert "### ends.py" in edit
    assert "def ends" in edit
    pair = next(item for item in TASKS if item["id"] == "pair")
    repair = repair_ask("the test file failed", list(pair["parts"]))
    assert "def person" in repair and "def greet" in repair
    assert "function only" not in repair
    assert pair["banned"] not in repair
