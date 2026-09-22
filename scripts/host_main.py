"""Disk writer kernel. Self-heal first, then host."""
from __future__ import annotations
import json, os, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\Users\Otcde\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]

def _git() -> str:
    for p in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if Path(p).is_file():
            return p
    return "git"

def _pull(root: Path) -> None:
    if os.name != "nt":
        return
    kw: Dict[str, Any] = {"cwd": str(root), "timeout": 120, "capture_output": True, "creationflags": 0x08000000}
    git = _git()
    try:
        subprocess.run([git, "fetch", "origin"], **kw)
        pull = subprocess.run([git, "pull", "--ff-only", "origin", "main"], **kw)
        if pull.returncode != 0:
            subprocess.run([git, "reset", "--hard", "origin/main"], **kw)
    except Exception:
        return

def _ensure_daemon(root: Path) -> Dict[str, Any]:
    pid_path = root / "memory" / "daemon" / "daemon.pid"
    if pid_path.is_file():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            if pid > 0:
                return {"ok": True, "already": pid}
        except Exception:
            pass
    pyw = root / ".venv" / "Scripts" / "pythonw.exe"
    py = pyw if pyw.is_file() else Path(root / ".venv" / "Scripts" / "python.exe")
    script = root / "scripts" / "ether_daemon.py"
    if not script.is_file():
        return {"ok": False, "error": "no_daemon"}
    env = os.environ.copy()
    env["ETHER_ROOT"] = str(root)
    env["ETHER_DAEMON_DASHBOARD"] = "0"
    env["ETHER_FLYWHEEL_PUSH"] = "1"
    env["PYTHONPATH"] = str(root)
    try:
        subprocess.Popen(
            [str(py), str(script)],
            cwd=str(root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        return {"ok": True, "spawned": True, "dash": False}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}

def tick() -> Dict[str, Any]:
    root = _root()
    os.environ["ETHER_ROOT"] = str(root)
    row: Dict[str, Any] = {"ts": datetime.now(timezone.utc).isoformat(), "root": str(root), "os": os.name}
    if os.name == "nt":
        _pull(root)
        try:
            from scripts.self_heal import arm
            row["heal"] = arm()
        except Exception as exc:
            row["heal_error"] = type(exc).__name__
        try:
            from scripts.start_runner import start_runner
            row["runner"] = start_runner()
        except Exception as exc:
            row["runner_error"] = type(exc).__name__
        row["daemon"] = _ensure_daemon(root)
        try:
            from scripts.app_keepalive import ensure_keepalive
            row["keepalive"] = ensure_keepalive(root)
        except Exception as exc:
            row["keepalive_error"] = type(exc).__name__
        try:
            from scripts.origin_publish import publish
            row["publish"] = publish(root, message="1650 host_main")
        except Exception as exc:
            row["publish_error"] = type(exc).__name__
    else:
        row["note"] = "observe_only"
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "host_main.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row

if __name__ == "__main__":
    print(json.dumps(tick(), default=str))
