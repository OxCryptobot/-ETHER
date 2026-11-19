"""One control surface for the 1650 writer. Called by scripts/host.cmd.

    host.cmd install    idempotent: remove legacy starters, register ETHER-Host, start, status
    host.cmd start      clear the stop file, run the ETHER-Host task (or spawn the supervisor)
    host.cmd stop       sticky stop: write artifacts/host.stop, wait, then force
    host.cmd restart    stop + start
    host.cmd status     JSON: task, supervisor, app_alive age, LIVE verdict, Ollama, next_goal
    host.cmd once       one writer pass in the foreground (debug)
    host.cmd uninstall  delete ETHER-Host and stop
    host.cmd ci         used by autonomy-host.yml: ensure the supervisor, never a second writer

Exit codes: 0 ok, 1 failure, 2 usage, 10 (ci only) = ETHER-Host not installed yet,
caller may run the legacy inline tick during the transition.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from scripts.host_lock import is_locked, lock_pid  # noqa: E402

TASK = "ETHER-Host"
# Every scheduled task an older launcher ever registered. ETHER-Host is never here.
LEGACY_TASKS = (
    "ETHER-Daemon",
    "ETHER-Ensure",
    "ETHER-keepalive",
    "ETHER-keepalive-5m",
    "ETHER-keepalive-boot",
    "ETHER-Keepalive-Logon",
    "ETHER-Writer",
    "ETHER-App",
    "ETHER-Autonomy",
    "ETHER-Flywheel",
    "ETHER-Watchdog",
)
LEGACY_PROCS = ("ether_keepalive.py", "ether_daemon.py", "ether_host.py", "ether_app.py", "autonomy.ps1",
                "start_ether_host.ps1", "start_daemon.ps1", "ensure_daemon.ps1")
STARTUP_GLOBS = ("ETHER*.vbs", "ETHER*.lnk", "ether*.vbs", "ether*.lnk")

Runner = Callable[[List[str]], subprocess.CompletedProcess]


def root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    return HERE


def _run(argv: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
    kw: Dict[str, Any] = {"capture_output": True, "text": True, "timeout": timeout, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000
    try:
        return subprocess.run(argv, **kw)
    except Exception as exc:  # missing schtasks off Windows, timeouts
        return subprocess.CompletedProcess(argv, 127, "", type(exc).__name__)


def art(base: Path) -> Path:
    p = Path(base) / "artifacts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pythonw(base: Path) -> Path:
    return Path(base) / ".venv" / "Scripts" / "pythonw.exe"


def task_xml(base: Path, user: str = "", start: Optional[datetime] = None, boot_s4u: bool = False,
             include_boot: bool = True) -> str:
    """Task Scheduler 1.2 XML for the ONE start method. All paths derive from base."""
    base = Path(base)
    start = start or datetime.now().replace(microsecond=0)
    cmd = escape(str(pythonw(base)))
    arg = escape('"' + str(base / "scripts" / "host_supervisor.py") + '"')
    wd = escape(str(base))
    uid = f"<UserId>{escape(user)}</UserId>" if user else ""
    logon_type = "S4U" if boot_s4u else "InteractiveToken"
    boot = "<BootTrigger><Enabled>true</Enabled><Delay>PT1M</Delay></BootTrigger>" if include_boot else ""
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ETHER writer supervisor (scripts/host_supervisor.py). The only start method. Logon + boot + 5-min ensure; a second copy exits on the OS lock.</Description>
    <URI>\\{TASK}</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled>{uid}</LogonTrigger>
    {boot}
    <TimeTrigger>
      <Repetition><Interval>PT5M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>{start.isoformat()}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">{uid}<LogonType>{logon_type}</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{cmd}</Command>
      <Arguments>{arg}</Arguments>
      <WorkingDirectory>{wd}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def write_task_xml(base: Path, text: str) -> Path:
    path = art(base) / f"{TASK}.xml"
    path.write_bytes(text.encode("utf-16"))  # schtasks /XML wants UTF-16 with BOM
    return path


def task_installed(run: Runner = _run) -> bool:
    return run(["schtasks", "/Query", "/TN", TASK]).returncode == 0


def supervisor(base: Path) -> Dict[str, Any]:
    lock = art(base) / "host.lock"
    up = is_locked(lock)
    return {"running": up, "pid": lock_pid(lock) if up else 0}


def _read(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def status(base: Optional[Path] = None, run: Runner = _run) -> Dict[str, Any]:
    base = Path(base or root())
    a = art(base)
    alive = _read(a / "app_alive.json")
    sup_state = _read(a / "supervisor.json")
    host = _read(a / "host_main.json")
    try:
        from scripts.live_status import judge
        verdict = judge(str(alive.get("ts") or ""), bool(alive.get("ollama")))
    except Exception as exc:
        verdict = {"error": type(exc).__name__}
    try:
        from scripts.live_host import ollama_up
        oll = ollama_up()
    except Exception:
        oll = None
    try:
        from scripts.host_main import _git
        git = _git()
    except Exception:
        git = "git"
    head = run([git, "-C", str(base), "rev-parse", "--short", "HEAD"])
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "root": str(base),
        "task": {"name": TASK, "installed": task_installed(run) if os.name == "nt" else None},
        "supervisor": {**supervisor(base), "state": sup_state.get("state"), "cycle": sup_state.get("cycle"),
                       "failures": sup_state.get("failures"), "last_ts": sup_state.get("ts")},
        "stop_file": (a / "host.stop").is_file(),
        "app_alive_ts": alive.get("ts"),
        "app_alive_ollama": alive.get("ollama"),
        "live": verdict,
        "ollama_now": oll,
        "next_goal": host.get("next_goal"),
        "head": (head.stdout or "").strip() or None,
        "note": "LIVE = app_alive under 6h AND ollama. A running supervisor alone is not LIVE.",
    }
    return row


def legacy_pids(run: Runner = _run) -> List[int]:
    """Pids of old starters (keepalive/daemon/ether_host). Windows only."""
    if os.name != "nt":
        return []
    like = " -or ".join(f"$_.CommandLine -like '*{n}*'" for n in LEGACY_PROCS)
    ps = ("Get-CimInstance Win32_Process | Where-Object { " + like + " } | "
          "ForEach-Object { $_.ProcessId }")
    out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps])
    pids = []
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit() and int(line) != os.getpid():
            pids.append(int(line))
    return pids


def disable_startup_items(home: Optional[Path] = None) -> List[str]:
    """Rename old Startup-folder launchers (ETHER-host.vbs etc.) to *.retired. Reversible."""
    appdata = os.environ.get("APPDATA") or str((home or Path.home()) / "AppData" / "Roaming")
    folder = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    moved: List[str] = []
    if not folder.is_dir():
        return moved
    seen = set()
    for pat in STARTUP_GLOBS:
        for p in folder.glob(pat):
            if p in seen or not p.is_file():
                continue
            seen.add(p)
            try:
                p.rename(p.with_name(p.name + ".retired"))
                moved.append(p.name)
            except OSError:
                pass
    return moved


def remove_legacy(base: Path, run: Runner = _run) -> Dict[str, Any]:
    row: Dict[str, Any] = {"tasks": {}, "killed": [], "startup": []}
    for name in LEGACY_TASKS:
        assert name.lower() != TASK.lower()
        row["tasks"][name] = run(["schtasks", "/Delete", "/TN", name, "/F"]).returncode
    held = supervisor(base).get("pid") or 0
    for pid in legacy_pids(run):
        if pid == held:
            continue
        rc = run(["taskkill", "/PID", str(pid), "/T", "/F"]).returncode
        row["killed"].append({"pid": pid, "rc": rc})
    row["startup"] = disable_startup_items()
    return row


def spawn_supervisor(base: Path) -> Dict[str, Any]:
    pyw = pythonw(base)
    py = str(pyw) if pyw.is_file() else sys.executable
    argv = [py, str(Path(base) / "scripts" / "host_supervisor.py")]
    env = dict(os.environ, ETHER_ROOT=str(base), PYTHONPATH=str(base))
    try:
        from scripts.win_quiet import popen_hidden
        popen_hidden(argv, cwd=str(base), env=env)
        return {"ok": True, "via": "spawn"}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


def wait_running(base: Path, want: bool, secs: float, sleep: Callable[[float], None] = time.sleep) -> bool:
    end = time.monotonic() + secs
    while True:
        if supervisor(base)["running"] == want:
            return True
        if time.monotonic() >= end:
            return False
        sleep(1.0)


def start(base: Optional[Path] = None, run: Runner = _run, wait_s: float = 30) -> Dict[str, Any]:
    base = Path(base or root())
    stop = art(base) / "host.stop"
    try:
        stop.unlink()
    except FileNotFoundError:
        pass
    if supervisor(base)["running"]:
        return {"ok": True, "note": "already_running", **supervisor(base)}
    if os.name == "nt" and task_installed(run):
        rc = run(["schtasks", "/Run", "/TN", TASK]).returncode
        how: Dict[str, Any] = {"via": "task", "rc": rc}
        if rc != 0:
            how = {**how, **spawn_supervisor(base)}
    else:
        how = spawn_supervisor(base)
    up = wait_running(base, True, wait_s)
    return {"ok": up, **how, **supervisor(base)}


def stop(base: Optional[Path] = None, run: Runner = _run, wait_s: float = 90, force: bool = True) -> Dict[str, Any]:
    base = Path(base or root())
    (art(base) / "host.stop").write_text(datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8")
    sup = supervisor(base)
    if not sup["running"]:
        return {"ok": True, "note": "not_running", "sticky": True}
    if wait_running(base, False, wait_s):
        return {"ok": True, "note": "stopped", "sticky": True}
    if not force:
        return {"ok": False, "note": "still_running", "pid": sup["pid"]}
    if os.name == "nt":
        run(["schtasks", "/End", "/TN", TASK])
        if sup["pid"]:
            run(["taskkill", "/PID", str(sup["pid"]), "/T", "/F"])
    elif sup["pid"]:
        try:
            os.kill(int(sup["pid"]), 15)
        except OSError:
            pass
    ok = wait_running(base, False, 15)
    return {"ok": ok, "note": "forced" if ok else "stuck", "sticky": True}


def install(base: Optional[Path] = None, run: Runner = _run, boot_s4u: bool = False) -> Dict[str, Any]:
    base = Path(base or root())
    row: Dict[str, Any] = {"root": str(base)}
    if os.name != "nt":
        return {**row, "ok": False, "error": "windows_only", "xml_preview": task_xml(base)[:200]}
    if not pythonw(base).is_file():
        return {**row, "ok": False, "error": "no_venv_pythonw",
                "fix": r"scripts\host.cmd setup"}
    row["legacy"] = remove_legacy(base, run)
    user = "\\".join(x for x in (os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")) if x)
    xml = write_task_xml(base, task_xml(base, user=user, boot_s4u=boot_s4u))
    created = run(["schtasks", "/Create", "/TN", TASK, "/XML", str(xml), "/F"])
    row["create"] = {"rc": created.returncode, "err": (created.stderr or "").strip()[-300:]}
    if created.returncode != 0 and not boot_s4u:
        # Some builds refuse a boot trigger on an interactive-token task; logon + 5-min still cover reboot.
        xml = write_task_xml(base, task_xml(base, user=user, include_boot=False))
        created = run(["schtasks", "/Create", "/TN", TASK, "/XML", str(xml), "/F"])
        row["create_retry_no_boot"] = {"rc": created.returncode, "err": (created.stderr or "").strip()[-300:]}
    if created.returncode != 0:
        row["ok"] = False
        if boot_s4u:
            row["hint"] = "--boot needs an elevated (Run as administrator) prompt"
        return row
    row["start"] = start(base, run)
    row["status"] = status(base, run)
    row["ok"] = bool(row["start"].get("ok"))
    return row


def uninstall(base: Optional[Path] = None, run: Runner = _run) -> Dict[str, Any]:
    base = Path(base or root())
    out = stop(base, run)
    rc = run(["schtasks", "/Delete", "/TN", TASK, "/F"]).returncode if os.name == "nt" else None
    return {"ok": True, "stop": out, "delete_rc": rc}


def ci(base: Optional[Path] = None, run: Runner = _run) -> int:
    """autonomy-host.yml: make sure the ONE supervisor runs; never tick as a second writer."""
    base = Path(base or root())
    if supervisor(base)["running"]:
        print(json.dumps({"ok": True, "note": "supervisor_alive", **supervisor(base)}))
        return 0
    if (art(base) / "host.stop").is_file():
        print(json.dumps({"ok": True, "note": "operator_stop_respected"}))
        return 0
    if os.name == "nt" and task_installed(run):
        # Task Scheduler owns the process, so it outlives this Actions job.
        rc = run(["schtasks", "/Run", "/TN", TASK]).returncode
        up = wait_running(base, True, 20)
        print(json.dumps({"ok": up, "note": "task_started" if up else "task_start_failed", "rc": rc}))
        return 0 if up else 1
    print(json.dumps({"ok": False, "note": "ETHER-Host not installed; legacy inline tick allowed"}))
    return 10


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0].lower() if args else "status"
    base = root()
    os.environ["ETHER_ROOT"] = str(base)
    if cmd == "ci":
        return ci(base)
    if cmd == "install":
        out = install(base, boot_s4u="--boot" in args)
    elif cmd == "uninstall":
        out = uninstall(base)
    elif cmd == "start":
        out = start(base)
    elif cmd == "stop":
        out = stop(base, force="--no-force" not in args)
    elif cmd == "restart":
        stop(base)
        out = start(base)
    elif cmd == "status":
        out = status(base)
        print(json.dumps(out, indent=2, default=str))
        return 0
    elif cmd == "once":
        from scripts.host_main import tick
        out = tick()
    else:
        print(__doc__)
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
