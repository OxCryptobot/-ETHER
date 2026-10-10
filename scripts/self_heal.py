"""Stop the old popup tasks. Arm one hidden runner watch. That watch does not run git."""
from __future__ import annotations
import os, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FLAGS = 0x08000000
WATCH = "ETHER-RunnerWatch"
POPUP_TASKS = (
    "ETHER-Ensure",
    "ETHER-keepalive",
    "ETHER-keepalive-5m",
    "ETHER-keepalive-boot",
    "ETHER-Daemon",
)


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


def watch_python(root: Path) -> Optional[Path]:
    pyw = Path(root) / ".venv" / "Scripts" / "pythonw.exe"
    return pyw if pyw.is_file() else None


def watch_argv(root: Path, pyw: Path) -> List[str]:
    script = Path(root) / "scripts" / "runner_watch.py"
    return [
        "schtasks",
        "/Create",
        "/TN",
        WATCH,
        "/TR",
        f'"{pyw}" "{script}"',
        "/SC",
        "MINUTE",
        "/MO",
        "5",
        "/F",
        "/RL",
        "LIMITED",
    ]


def _run(argv: List[str], timeout: int = 30) -> int:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, creationflags=FLAGS)
        return int(p.returncode)
    except Exception:
        return 1

def arm() -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "os": os.name,
        "ok": True,
        "armed": False,
        "note": "observe_only" if os.name != "nt" else "no_pythonw",
    }
    if os.name != "nt":
        return row
    stopped = {}
    for name in POPUP_TASKS:
        stopped[name] = _run(["schtasks", "/Delete", "/TN", name, "/F"])
    row["stopped"] = stopped
    root = _root()
    pyw = watch_python(root)
    if pyw is None:
        row["watch"] = {"ok": False, "note": "no_pythonw"}
    else:
        rc = _run(watch_argv(root, pyw))
        row["watch"] = {"ok": rc == 0, "task": WATCH, "rc": rc}
        row["armed"] = rc == 0
        row["note"] = "runner_watch" if rc == 0 else "watch_failed"
    try:
        from scripts.runner_register import register as register_runner
        row["register"] = register_runner()
    except Exception as exc:
        row["register_error"] = type(exc).__name__
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "self_heal.json").write_text(__import__("json").dumps(row, indent=2) + "\n", encoding="utf-8")
    return row