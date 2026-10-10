from pathlib import Path

from scripts.runner_watch import needs_start
from scripts.self_heal import POPUP_TASKS, WATCH, arm, watch_argv


def test_self_heal_observe_only() -> None:
    row = arm()
    assert row.get("ok") is True
    assert row.get("note") == "observe_only" or row.get("os") == "nt"


def test_the_watch_is_not_a_popup_task(tmp_path: Path) -> None:
    assert WATCH not in POPUP_TASKS
    pyw = tmp_path / ".venv" / "Scripts" / "pythonw.exe"
    argv = watch_argv(tmp_path, pyw)
    joined = " ".join(argv)
    assert WATCH in argv
    assert "git" not in joined
    assert "pythonw.exe" in joined
    assert "runner_watch.py" in joined
    assert "/SC" in argv and "MINUTE" in argv


def test_a_missing_listener_needs_a_start() -> None:
    assert needs_start("INFO: No tasks are running") is True
    assert needs_start("Runner.Listener.exe    1234 Console    1  40,000 K") is False

