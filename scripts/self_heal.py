"""Permanent self-heal. No XML. No operator. Arms logon+boot+5m+HKCU Run+Startup."""
from __future__ import annotations
import os, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

FLAGS = 0x08000000

def keepalive_vbs(pyw: Path, keep: Path) -> str:
    """Two real lines. A literal backslash-n is not valid VBScript."""
    return (
        'Set s=CreateObject("WScript.Shell")\n'
        f's.Run """{pyw}"" ""{keep}""", 0, False\n'
    )


def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\\Users\\Otcde\\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]

def _run(argv: List[str], timeout: int = 30) -> int:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, creationflags=FLAGS)
        return int(p.returncode)
    except Exception:
        return 1

def arm() -> Dict[str, Any]:
    row: Dict[str, Any] = {"ts": datetime.now(timezone.utc).isoformat(), "os": os.name, "ok": False, "armed": False}
    if os.name != "nt":
        row["note"] = "observe_only"
        row["ok"] = True
        return row
    try:
        from scripts.runner_register import register as register_runner
        row["register"] = register_runner()
    except Exception as exc:
        row["register_error"] = type(exc).__name__
    root = _root()
    pyw = root / ".venv" / "Scripts" / "pythonw.exe"
    if not pyw.is_file():
        pyw = root / ".venv" / "Scripts" / "python.exe"
    keep = root / "scripts" / "ether_keepalive.py"
    vbs_path = root / "scripts" / "ETHER-host.vbs"
    try:
        vbs_path.write_text(keepalive_vbs(pyw, keep), encoding="ascii", errors="replace")
    except Exception as exc:
        row["vbs_error"] = type(exc).__name__
    tr = f'wscript.exe //B "{vbs_path}"'
    runner_dir = Path(os.environ.get("ETHER_RUNNER_DIR") or r"C:\\actions-runner")
    run_cmd = runner_dir / "run.cmd"
    runner_tr = f'cmd.exe /c cd /d "{runner_dir}" && run.cmd'
    tasks = [
        (["schtasks", "/Create", "/TN", "ETHER-keepalive", "/TR", tr, "/SC", "ONLOGON", "/F"], "logon"),
        (["schtasks", "/Create", "/TN", "ETHER-keepalive-5m", "/TR", tr, "/SC", "MINUTE", "/MO", "5", "/F"], "5m"),
        (["schtasks", "/Create", "/TN", "ETHER-keepalive-boot", "/TR", tr, "/SC", "ONSTART", "/F"], "boot"),
    ]
    if run_cmd.is_file():
        tasks.extend([
            (["schtasks", "/Create", "/TN", "ETHER-Runner", "/TR", runner_tr, "/SC", "ONLOGON", "/F"], "runner_logon"),
            (["schtasks", "/Create", "/TN", "ETHER-Runner-5m", "/TR", runner_tr, "/SC", "MINUTE", "/MO", "5", "/F"], "runner_5m"),
        ])
    armed: Dict[str, int] = {}
    for argv, key in tasks:
        armed[key] = _run(argv)
    row["tasks"] = armed
    _run(["reg", "add", r"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", "/v", "ETHER-host", "/t", "REG_SZ", "/d", tr, "/f"])
    try:
        startup = Path(os.environ.get("APPDATA") or "") / r"Microsoft\\Windows\\Start Menu\\Programs\\Startup"
        if startup.is_dir():
            (startup / "ETHER-host.vbs").write_text(keepalive_vbs(pyw, keep), encoding="ascii", errors="replace")
            row["startup"] = True
    except Exception as exc:
        row["startup_error"] = type(exc).__name__
    svc = runner_dir / "svc.cmd"
    if svc.is_file():
        _run(["cmd.exe", "/c", str(svc), "start"], timeout=40)
        row["svc"] = True
    if run_cmd.is_file():
        try:
            subprocess.Popen(
                ["cmd.exe", "/c", str(run_cmd)],
                cwd=str(runner_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=FLAGS,
            )
            row["run_cmd"] = True
        except Exception as exc:
            row["run_cmd_error"] = type(exc).__name__
    _run(["schtasks", "/Run", "/TN", "ETHER-keepalive"])
    _run(["schtasks", "/Run", "/TN", "ETHER-Runner"])
    row["ok"] = True
    row["armed"] = True
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "self_heal.json").write_text(__import__("json").dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
