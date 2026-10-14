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


def test_a_one_line_traceback_keeps_the_other_cases() -> None:
    from core.kernel.read_gate import with_cases

    failing = "ends(ether) returned e, expected er; ends(abc) returned a, expected ac"
    note = with_cases("AssertionError", failing)
    assert "abc" in note and "AssertionError" in note
    assert with_cases(failing, failing) == failing


def test_the_same_failure_is_not_repaired_twice() -> None:
    from core.kernel.read_gate import fresh_note

    failing = "ends(ether) returned e, expected er"
    assert fresh_note(failing, [], failing) == ""
    first = "ends(abc) returned bc, expected ac"
    assert fresh_note(first, [], failing) == first
    assert fresh_note(first, [first], failing) == ""


def test_a_new_case_list_beats_the_same_traceback() -> None:
    from core.kernel.read_gate import pick_note

    failing = "ends(ether) returned e, expected er; ends(abc) returned a, expected ac"
    changed = "ends(ether) returned r, expected er; ends(abc) returned c, expected ac"
    assert pick_note(changed, "AssertionError", failing) == changed
    assert "abc" in pick_note(failing, "AssertionError", failing)


def test_the_lesson_is_the_failure_and_not_the_patch() -> None:
    from core.kernel.edit_memory import lesson_line

    assert "bc" in lesson_line("ends(abc) returned bc, expected ac", "s[-1]")
    assert lesson_line("return s[-1]", "s[-1]") == ""


def test_a_day_note_does_not_erase_the_edit_lesson(tmp_path) -> None:
    from core.kernel.edit_memory import recall, remember

    remember(tmp_path, "ends(abc) returned bc, expected ac")
    remember(tmp_path, "day 2026-10-14: unknown", "day")
    assert recall(tmp_path) == "ends(abc) returned bc, expected ac"


def test_whitespace_does_not_make_a_failed_function_new() -> None:
    from core.kernel.product_loop import body_key

    one = "def ends(s):\n    return s[-2:]\n"
    two = "def ends(s):\n  return s[-2:]\n"
    assert body_key(one) == body_key(two)
    assert body_key(one) != body_key("def ends(s):\n    return s[0]\n")


def test_the_live_bench_is_not_the_old_scoreboard(tmp_path) -> None:
    from core.kernel.curriculum import bench, mark_passed

    mark_passed(tmp_path, "add")
    row = bench(tmp_path, {"task": "ends", "honest": False, "reason": "repeated"})
    assert row["passed_marks"] == ["add"]
    assert row["last_honest"] is False
    assert row["open"] == "clamp"
    assert "scoreboard_latest" in row["note"]
    assert (tmp_path / "artifacts" / "agent_bench.json").is_file()
