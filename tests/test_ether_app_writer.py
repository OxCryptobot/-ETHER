"""Exe writer contract: git is a runner, queue is jobs/pending, no installer."""
from scripts.ether_app import _git, dashboard_status, git_run, update_self


def test_git_is_path_not_runner() -> None:
    assert isinstance(_git(), str)


def test_git_run_exists() -> None:
    assert callable(git_run)


def test_update_self_does_not_download_exe() -> None:
    row = update_self()
    assert row["ok"] is True
    assert row.get("pending") in {None, ""}
    assert "no second installer" in str(row.get("note") or "").lower() or "git pull" in str(row.get("note") or "").lower()


def test_status_queue_uses_jobs_pending() -> None:
    snap = dashboard_status()
    assert "queue" in snap
    assert isinstance(snap["queue"], list)
