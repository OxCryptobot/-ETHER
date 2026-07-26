#!/usr/bin/env python3
"""@ETHER single-process daemon — dashboard + flywheel + batch in ONE process.

Do NOT open multiple PowerShell windows. One of:
  A) Scheduled Task ETHER-Daemon  (zero windows)
  B) python scripts/ether_daemon.py  (one window)
"""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ.setdefault("ETHER_GIT_RESET_OK", "1")
os.environ.setdefault("ETHER_PULL_SOFT", "1")
os.environ.setdefault("ETHER_FLYWHEEL_PUSH", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")

from core.dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

PY = sys.executable
INTERVAL = int(os.getenv("ETHER_DAEMON_INTERVAL", os.getenv("ETHER_FLYWHEEL_INTERVAL", "900")))
BATCH_INTERVAL = int(os.getenv("ETHER_BATCH_INTERVAL", "1800"))
RUN_DASH = os.getenv("ETHER_DAEMON_DASHBOARD", "1") == "1"
RUN_FLYWHEEL = os.getenv("ETHER_DAEMON_FLYWHEEL", "1") == "1"
RUN_BATCH = os.getenv("ETHER_DAEMON_BATCH", "1") == "1"
PORT = int(os.getenv("ETHER_DASH_PORT", "8787"))

PID_PATH = ROOT / "memory" / "daemon" / "daemon.pid"
HB_PATH = ROOT / "memory" / "daemon" / "heartbeat.txt"
LOG_PATH = ROOT / "memory" / "daemon" / "daemon.log"
_stop = threading.Event()


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def acquire_lock() -> bool:
    """Only one daemon process allowed."""
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    if PID_PATH.exists():
        try:
            old = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            old = -1
        if old != os.getpid() and _pid_alive(old):
            log(f"ABORT: another daemon already running (pid={old})")
            log("Stop it: powershell -File scripts\\stop_daemon.ps1")
            return False
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    def _clear():
        try:
            if PID_PATH.exists() and PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_PATH.unlink(missing_ok=True)
        except Exception:
            pass

    atexit.register(_clear)
    return True


def heartbeat() -> None:
    try:
        HB_PATH.parent.mkdir(parents=True, exist_ok=True)
        HB_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def run_cmd(args: list[str], timeout: int = 3600) -> int:
    try:
        p = subprocess.run(args, cwd=str(ROOT), env=os.environ.copy(), timeout=timeout)
        return p.returncode
    except subprocess.TimeoutExpired:
        log(f"timeout: {args}")
        return -1
    except Exception as e:
        log(f"cmd error {args}: {e}")
        return -1


def flywheel_loop() -> None:
    log(f"flywheel loop interval={INTERVAL}s")
    while not _stop.is_set():
        heartbeat()
        log("flywheel cycle start")
        code = run_cmd(
            [
                PY,
                "-m",
                "cli.main",
                "flywheel",
                "--push",
                "--min-confidence",
                os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7"),
                "--max-retries",
                os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3"),
            ],
            timeout=2400,
        )
        log(f"flywheel cycle exit={code}")
        for _ in range(max(60, INTERVAL)):
            if _stop.is_set():
                return
            time.sleep(1)
            if int(time.time()) % 30 == 0:
                heartbeat()


def batch_loop() -> None:
    log(f"batch worker interval={BATCH_INTERVAL}s")
    while not _stop.is_set():
        heartbeat()
        log("batch worker tick")
        code = run_cmd([PY, "scripts/batch_worker.py"], timeout=3600)
        log(f"batch worker exit={code}")
        for _ in range(max(120, BATCH_INTERVAL)):
            if _stop.is_set():
                return
            time.sleep(1)


def dashboard_loop() -> None:
    log(f"dashboard :{PORT}")
    try:
        import uvicorn

        uvicorn.run(
            "dashboard.app:app",
            host="127.0.0.1",
            port=PORT,
            reload=False,
            log_level="warning",
        )
    except Exception as e:
        log(f"dashboard stopped: {e}")


def main() -> int:
    print("=" * 60)
    print("  @ETHER DAEMON  — ONE process (not 4 windows)")
    print(f"  root={ROOT}")
    print(f"  flywheel={RUN_FLYWHEEL} batch={RUN_BATCH} dash={RUN_DASH}")
    print("  Ctrl+C to stop")
    print("=" * 60)

    if not acquire_lock():
        return 2

    heartbeat()

    if RUN_DASH:
        threading.Thread(target=dashboard_loop, name="dashboard", daemon=True).start()
        time.sleep(1.5)
    if RUN_FLYWHEEL:
        threading.Thread(target=flywheel_loop, name="flywheel", daemon=True).start()
    if RUN_BATCH:
        threading.Thread(target=batch_loop, name="batch", daemon=True).start()

    def _sig(*_a):
        log("signal stop")
        _stop.set()

    signal.signal(signal.SIGINT, _sig)
    try:
        signal.signal(signal.SIGTERM, _sig)
    except Exception:
        pass

    try:
        while not _stop.is_set():
            heartbeat()
            time.sleep(5)
    except KeyboardInterrupt:
        _stop.set()
    log("daemon exit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
