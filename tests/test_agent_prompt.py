from core.kernel.agent_prompt import EDIT, SYSTEM, messages


def test_the_prompt_fits_a_4b_and_speaks_the_parser() -> None:
    assert len(SYSTEM) < 500
    assert len(EDIT) < 500
    assert "READ:" in SYSTEM
    assert "READ:" not in EDIT
    assert "complete function" in EDIT
    for leaked in ("return a + b", "s[0] + s[-1]", "return 'ada'", "hi ada"):
        assert leaked not in SYSTEM
        assert leaked not in EDIT
    sent = messages("Failing cases:\nends")
    assert sent[0]["content"] == SYSTEM
    edit = messages("def ends", edit=True)
    assert edit[0]["content"] == EDIT
    assert edit[1] == {"role": "user", "content": "def ends"}


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


def test_a_traceback_is_a_repair_note_and_the_patch_is_not() -> None:
    from core.kernel.read_gate import failure_note

    note = failure_note("the test file failed", "NameError: name 'person' is not defined")
    assert "person" in note
    assert failure_note("the test file failed", "the test file failed") == ""
    assert failure_note("the test file failed", "return 'ada'", "return 'ada'") == ""
