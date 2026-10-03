"""The agent is one process. It does not commit, and a checker cannot write source."""
import json
from pathlib import Path

from core.kernel.agent import cycle


def test_without_hands_it_only_observes(tmp_path: Path) -> None:
    row = cycle(tmp_path, hands=False)
    assert row["decision"] == "observe"
    assert row["stages"] == ["perceive", "decide", "remember"]
    assert row["writers"] == []
    assert row["git"] is False
    assert row["honest"] is False


def test_hands_edit_then_verify_then_remember(tmp_path: Path) -> None:
    src = tmp_path / "add.py"
    src.write_text("return a - b\n", encoding="utf-8")

    def edit():
        return {"ts": "t1", "honest": True, "ok": True, "tests_ok": True, "tools": ["replace_once"]}

    row = cycle(tmp_path, hands=True, edit=edit)
    assert row["stages"] == ["perceive", "decide", "act", "verify", "remember"]
    assert row["honest"] is True
    assert row["writers"] == ["edit_tx"]
    assert row["git"] is False
    assert row["scale"]["checker_writes"] == 0
    assert src.read_text(encoding="utf-8") == "return a - b\n"
    saved = json.loads((tmp_path / "artifacts" / "agent.json").read_text(encoding="utf-8"))
    assert saved["decision"] == "edit"


def test_two_passes_stay_read_only(tmp_path: Path) -> None:
    def edit_one():
        return {"ts": "t1", "honest": True, "ok": True, "tests_ok": True}

    def edit_two():
        return {"ts": "t2", "honest": True, "ok": True, "tests_ok": True}

    cycle(tmp_path, hands=True, edit=edit_one)
    row = cycle(tmp_path, hands=True, edit=edit_two)
    assert row["scale"]["repeatable"] is True
    assert row["git"] is False
