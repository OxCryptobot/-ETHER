"""Stop leftover 5-minute git tasks. Do not create new ones."""
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
    """No scheduled tasks, no startup script, no registry Run key."""
    row: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "os": os.name,
        "ok": True,
        "armed": False,
        "note": "observe_only" if os.name != "nt" else "no hidden startup",
    }
    if os.name == "nt":
        stopped = {}
        for name in (
            "ETHER-Ensure",
            "ETHER-keepalive",
            "ETHER-keepalive-5m",
            "ETHER-keepalive-boot",
            "ETHER-Daemon",
        ):
            stopped[name] = _run(["schtasks", "/Delete", "/TN", name, "/F"])
        row["stopped"] = stopped
        try:
            from scripts.runner_register import register as register_runner
            row["register"] = register_runner()
        except Exception as exc:
            row["register_error"] = type(exc).__name__
    root = _root()
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "self_heal.json").write_text(__import__("json").dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
