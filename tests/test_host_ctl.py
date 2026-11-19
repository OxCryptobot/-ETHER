"""host.cmd / host_ctl: one task, one installer, legacy cleanup, self-heal never kills ETHER-Host."""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from scripts import host_ctl
from scripts.host_lock import HostLock


def test_self_heal_never_stops_the_chosen_starter() -> None:
    from scripts.self_heal import HOST_TASK, POPUP_TASKS, PROTECTED_TASKS, stop_list

    assert HOST_TASK == host_ctl.TASK == "ETHER-Host"
    lowered = {n.lower() for n in stop_list()}
    for name in PROTECTED_TASKS:
        assert name.lower() not in lowered
    assert HOST_TASK.lower() not in {n.lower() for n in POPUP_TASKS}
    assert "etherhost" not in {n.lower().replace("-", "") for n in stop_list()}


def test_self_heal_and_installer_remove_the_legacy_tasks() -> None:
    from scripts.self_heal import stop_list

    for name in ("ETHER-Daemon", "ETHER-Ensure", "ETHER-keepalive", "ETHER-keepalive-5m", "ETHER-keepalive-boot"):
        assert name in stop_list()
        assert name in host_ctl.LEGACY_TASKS
    assert host_ctl.TASK not in host_ctl.LEGACY_TASKS


def test_task_xml_is_one_task_with_three_triggers_and_no_hardcoded_root(tmp_path: Path) -> None:
    base = tmp_path / "SomeUser" / "ETHER"
    xml = host_ctl.task_xml(base, user="PC\\me", start=datetime(2026, 1, 1))
    assert "Otcde" not in xml
    assert str(base / "scripts" / "host_supervisor.py") in xml
    assert str(base / ".venv" / "Scripts" / "pythonw.exe") in xml
    assert "<LogonTrigger>" in xml and "<BootTrigger>" in xml and "<Interval>PT5M</Interval>" in xml
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml
    assert "<RestartOnFailure>" in xml
    assert "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml
    assert "ether_keepalive" not in xml and "ether_daemon" not in xml
    assert "InteractiveToken" in xml
    assert "S4U" in host_ctl.task_xml(base, boot_s4u=True)
    assert "<BootTrigger>" not in host_ctl.task_xml(base, include_boot=False)


def test_task_xml_written_utf16(tmp_path: Path) -> None:
    p = host_ctl.write_task_xml(tmp_path, host_ctl.task_xml(tmp_path))
    raw = p.read_bytes()
    assert raw[:2] in (b"\xff\xfe", b"\xfe\xff")
    assert "ETHER-Host" in raw.decode("utf-16")


class FakeWin:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, argv, timeout=60):
        self.calls.append(list(argv))
        rc = 1 if argv[:2] == ["schtasks", "/Query"] else 0
        return subprocess.CompletedProcess(argv, rc, "", "")


def test_remove_legacy_deletes_every_legacy_task_and_never_ether_host(tmp_path: Path) -> None:
    fake = FakeWin()
    out = host_ctl.remove_legacy(tmp_path, fake)
    deleted = [c[3] for c in fake.calls if c[:2] == ["schtasks", "/Delete"]]
    assert set(deleted) == set(host_ctl.LEGACY_TASKS)
    assert host_ctl.TASK not in deleted
    assert set(out["tasks"]) == set(host_ctl.LEGACY_TASKS)


def test_startup_folder_launchers_are_retired_reversibly(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    folder.mkdir(parents=True)
    (folder / "ETHER-host.vbs").write_text("x", encoding="utf-8")
    (folder / "other.lnk").write_text("x", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    moved = host_ctl.disable_startup_items()
    assert moved == ["ETHER-host.vbs"]
    assert (folder / "ETHER-host.vbs.retired").is_file()
    assert (folder / "other.lnk").is_file()


def test_start_clears_sticky_stop_and_reports_running(tmp_path: Path, monkeypatch) -> None:
    art = host_ctl.art(tmp_path)
    (art / "host.stop").write_text("x", encoding="utf-8")
    holder = HostLock(art / "host.lock")

    def fake_spawn(base):
        holder.acquire()
        return {"ok": True, "via": "spawn"}

    monkeypatch.setattr(host_ctl, "spawn_supervisor", fake_spawn)
    try:
        out = host_ctl.start(tmp_path, FakeWin(), wait_s=2)
        assert out["ok"] is True and out["running"] is True
        assert not (art / "host.stop").exists()
        again = host_ctl.start(tmp_path, FakeWin(), wait_s=1)
        assert again["note"] == "already_running"
    finally:
        holder.release()


def test_stop_is_sticky_and_noop_when_down(tmp_path: Path) -> None:
    out = host_ctl.stop(tmp_path, FakeWin(), wait_s=0)
    assert out["ok"] is True and out["note"] == "not_running"
    assert (tmp_path / "artifacts" / "host.stop").is_file()


def test_ci_never_ticks_when_supervisor_alive(tmp_path: Path) -> None:
    holder = HostLock(host_ctl.art(tmp_path) / "host.lock")
    holder.acquire()
    try:
        assert host_ctl.ci(tmp_path, FakeWin()) == 0
    finally:
        holder.release()


def test_ci_respects_operator_stop(tmp_path: Path) -> None:
    (host_ctl.art(tmp_path) / "host.stop").write_text("x", encoding="utf-8")
    assert host_ctl.ci(tmp_path, FakeWin()) == 0


def test_ci_off_windows_without_task_allows_transition_tick(tmp_path: Path) -> None:
    assert host_ctl.ci(tmp_path, FakeWin()) == 10


def test_status_shape_and_live_needs_ollama(tmp_path: Path) -> None:
    out = host_ctl.status(tmp_path, FakeWin())
    for key in ("task", "supervisor", "stop_file", "live", "ollama_now", "next_goal", "app_alive_ts"):
        assert key in out
    assert out["supervisor"]["running"] is False
    assert out["live"]["live"] is False


def test_install_off_windows_refuses_honestly(tmp_path: Path) -> None:
    out = host_ctl.install(tmp_path, FakeWin())
    assert out["ok"] is False and out["error"] == "windows_only"


def test_host_cmd_and_installer_are_thin_and_portable() -> None:
    host = Path("scripts/host.cmd").read_bytes().decode("utf-8")
    inst = Path("scripts/install_host.cmd").read_bytes().decode("utf-8")
    assert "host_ctl.py" in host and "%~dp0" in host
    assert "Otcde" not in host and "Otcde" not in inst
    assert "host.cmd\" install" in inst
    assert "powershell" not in host.lower() and "powershell" not in inst.lower()


def test_workflow_only_ensures_the_supervisor() -> None:
    wf = Path(".github/workflows/autonomy-host.yml").read_text(encoding="utf-8")
    assert "scripts/host_ctl.py ci" in wf
    assert "-eq 10" in wf  # inline tick only while ETHER-Host is not installed
