"""Exe writer contract: git is a runner, queue is jobs/pending, no installer."""
from scripts.ether_app import _git, dashboard_status, git_run, update_self


def test_git_is_path_not_runner() -> None:
    assert isinstance(_git(), str)


def test_git_run_exists() -> None:
    assert callable(git_run)


def test_frozen_swap_uses_desktop_release() -> None:
    from pathlib import Path
    text = Path("scripts/ether_app.py").read_text(encoding="utf-8")
    assert "ETHER.exe.new" in text
    assert 'release", "download", "desktop"' in text
    assert "no_venv_python" in text
    spec = Path("scripts/ether_app.spec").read_text(encoding="utf-8")
    assert "scripts.host_main" in spec
    assert "upx=False" in spec
    row = update_self()
    assert row["ok"] is True
    assert row.get("pending") in {None, ""}
    assert "no second installer" in str(row.get("note") or "").lower() or "git pull" in str(row.get("note") or "").lower()


def test_status_queue_uses_jobs_pending() -> None:
    snap = dashboard_status()
    assert "queue" in snap
    assert isinstance(snap["queue"], list)


def test_shutdown_does_not_require_stop_ollama() -> None:
    import inspect
    from scripts import ether_app

    src = inspect.getsource(ether_app.shutdown)
    assert "stop_ollama" not in src


def test_main_keeps_host_thread() -> None:
    import inspect
    from scripts import ether_app

    src = inspect.getsource(ether_app.main)
    assert "daemon=False" in src
    assert "host.join()" in src
