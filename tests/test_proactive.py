"""A failed allowlisted job is retried once. Shells and repeats are not."""
import json
from pathlib import Path

from core.kernel.proactive import act


def _fail(root: Path, name: str, argv: list) -> None:
    dest = root / "artifacts" / "jobs" / "failed"
    dest.mkdir(parents=True)
    (dest / name).write_text(json.dumps({
        "id": name[:-5],
        "steps": [{"argv": argv, "timeout": 30}],
    }), encoding="utf-8")


def test_retries_one_failed_job_once(tmp_path: Path) -> None:
    _fail(tmp_path, "live_edit_tx_20261002.json", [".venv/Scripts/python.exe", "-m", "scripts.live_edit_tx"])
    first = act(tmp_path)
    assert first["queued"] is True
    assert (tmp_path / "artifacts" / "jobs" / "pending" / "retry_live_edit_tx_20261002.json").is_file()
    again = act(tmp_path)
    assert again["queued"] is False
    pending = list((tmp_path / "artifacts" / "jobs" / "pending").glob("*.json"))
    assert len(pending) == 1


def test_does_not_retry_a_shell(tmp_path: Path) -> None:
    _fail(tmp_path, "bad.json", ["powershell", "-c", "git push"])
    assert act(tmp_path)["queued"] is False
    assert not (tmp_path / "artifacts" / "jobs" / "pending").exists()
