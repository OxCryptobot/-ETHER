"""The ladder advances, and the prompt does not contain the answer."""
import json
from pathlib import Path

from core.kernel.curriculum import TASKS, checker_for, mark_passed, next_task


def test_prompt_does_not_contain_the_answer() -> None:
    for task in TASKS:
        assert task["banned"] not in task["prompt"]
        assert task["banned"] not in task["source"]


def test_fresh_root_starts_at_add(tmp_path: Path) -> None:
    task = next_task(tmp_path)
    assert task is not None and task["id"] == "add"


def test_two_honest_passes_skip_add(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "honest_history.json").write_text(json.dumps({
        "items": [{"ts": "t1", "honest": True}, {"ts": "t2", "honest": True}],
    }), encoding="utf-8")
    task = next_task(tmp_path)
    assert task is not None and task["id"] == "clamp"


def test_passed_task_is_not_repeated(tmp_path: Path) -> None:
    mark_passed(tmp_path, "add")
    mark_passed(tmp_path, "clamp")
    assert next_task(tmp_path)["id"] == "sign"
    mark_passed(tmp_path, "sign")
    assert next_task(tmp_path) is None


def test_checkers_reject_the_broken_source() -> None:
    for task in TASKS:
        assert checker_for(task["id"])(task["source"]) is False
    assert checker_for("clamp")("def clamp(n, lo, hi):\n    return min(max(n, lo), hi)\n") is True
    assert checker_for("sign")("def sign(n):\n    return (n > 0) - (n < 0)\n") is True
