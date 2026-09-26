"""Disk writer kernel. Self-heal, LIVE attach, evolve, publish."""
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

def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
        except Exception:
            return False
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def _pull(root: Path) -> None:
    if os.name != "nt":
        return
    from scripts.origin_publish import sync_writer
    def runner(argv: list) -> subprocess.CompletedProcess:
        kw: Dict[str, Any] = {"cwd": str(root), "timeout": 120, "capture_output": True, "text": True, "creationflags": 0x08000000}
        return subprocess.run(argv, **kw)
    try:
        sync_writer(root, _git(), runner)
    except Exception:
        return

def _ensure_daemon(root: Path) -> Dict[str, Any]:
    if os.environ.get("ETHER_IN_DAEMON") == "1":
        return {"ok": True, "note": "already_inside_daemon"}
    pid_path = root / "memory" / "daemon" / "daemon.pid"
    if pid_path.is_file():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            if _pid_alive(pid):
                return {"ok": True, "already": pid}
        except Exception:
            pass
        try:
            pid_path.unlink(missing_ok=True)
        except Exception:
            pass
    pyw = root / ".venv" / "Scripts" / "pythonw.exe"
    py = pyw if pyw.is_file() else Path(root / ".venv" / "Scripts" / "python.exe")
    script = root / "scripts" / "ether_daemon.py"
    if not script.is_file() or not py.is_file():
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
            from scripts.live_host import start_ollama, consume, ollama_up
            row["ollama_start"] = start_ollama()
            row["attach"] = consume({"cmd": "attach"})
            row["ollama"] = ollama_up()
        except Exception as exc:
            row["attach_error"] = type(exc).__name__
        try:
            from scripts.ether_app import mark_alive
            row["alive"] = mark_alive()
        except Exception as exc:
            row["alive_error"] = type(exc).__name__
        try:
            from scripts.drain_live_fifo import drain as drain_live
            row["live"] = drain_live()
        except Exception as exc:
            row["live_error"] = type(exc).__name__
        try:
            from scripts.ether_evolve import cycle
            row["evolve"] = cycle()
        except Exception as exc:
            row["evolve_error"] = type(exc).__name__
        if row.get("ollama"):
            try:
                from scripts.ether_role import tick as role_tick
                row["role"] = role_tick()
            except Exception as exc:
                row["role_error"] = type(exc).__name__
        try:
            from scripts.live_status import write as live_status
            row["live_status"] = live_status()
        except Exception as exc:
            row["live_status_error"] = type(exc).__name__
        try:
            from scripts.origin_publish import publish
            row["publish"] = publish(root, message="1650 host_main")
        except Exception as exc:
            row["publish_error"] = type(exc).__name__
    else:
        try:
            from scripts.ether_evolve import cycle
            row["evolve"] = cycle()
        except Exception as exc:
            row["evolve_error"] = type(exc).__name__
        row["note"] = "observe_only"
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "host_main.json").write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    return row

if __name__ == "__main__":
    print(json.dumps(tick(), default=str))
