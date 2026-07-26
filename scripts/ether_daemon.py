#!/usr/bin/env python3
"""@ETHER daemon — refuses to declare healthy when scoreboard stale."""

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

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ.setdefault("ETHER_GIT_RESET_OK", "1")
os.environ.setdefault("ETHER_PULL_SOFT", "1")
os.environ.setdefault("ETHER_FLYWHEEL_PUSH", "1")
os.environ.setdefault("ETHER_CURRICULUM", "1")
os.environ.setdefault("ETHER_EXPERIENCE", "1")
os.environ.setdefault("ETHER_BENCH_GUARDIAN", "1")
os.environ.setdefault("ETHER_BURST_ON_FAIL", "1")
os.environ.setdefault("ETHER_CURRICULUM_FAIL_RATE", "0.4")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")

try:
    from core.dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

PY = sys.executable
INTERVAL = int(os.getenv("ETHER_DAEMON_INTERVAL", os.getenv("ETHER_FLYWHEEL_INTERVAL", "900")))
BATCH_INTERVAL = int(os.getenv("ETHER_BATCH_INTERVAL", "1800"))
RECONCILE_EVERY = int(os.getenv("ETHER_RECONCILE_EVERY_N", "3"))
BENCH_EVERY = int(os.getenv("ETHER_BENCH_EVERY_N", "6"))
QUIZ_EVERY = int(os.getenv("ETHER_QUIZ_EVERY_N", "8"))
RUN_DASH = os.getenv("ETHER_DAEMON_DASHBOARD", "1") == "1"
RUN_FLYWHEEL = os.getenv("ETHER_DAEMON_FLYWHEEL", "1") == "1"
RUN_BATCH = os.getenv("ETHER_DAEMON_BATCH", "1") == "1"
PORT = int(os.getenv("ETHER_DASH_PORT", "8787"))

PID_PATH = ROOT / "memory" / "daemon" / "daemon.pid"
HB_PATH = ROOT / "memory" / "daemon" / "heartbeat.txt"
LOG_PATH = ROOT / "memory" / "daemon" / "daemon.log"
HEALTH_FLAG = ROOT / "memory" / "daemon" / "healthy.json"
_stop = threading.Event()
_cycle_n = 0


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

            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def acquire_lock() -> bool:
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    if PID_PATH.exists():
        try:
            old = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            old = -1
        if old > 0 and old != os.getpid() and _pid_alive(old):
            log(f"ABORT: daemon already running pid={old}")
            return False
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    def _clear() -> None:
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


def write_healthy_flag() -> dict:
    try:
        from core.health_metric import declare_healthy

        h = declare_healthy()
    except Exception as e:
        h = {"healthy": False, "reasons": [str(e)]}
    try:
        HEALTH_FLAG.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_FLAG.write_text(
            __import__("json").dumps({**h, "ts": datetime.now(timezone.utc).isoformat()}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    if not h.get("healthy"):
        log(f"NOT HEALTHY: {h.get('reasons')}")
    else:
        log("HEALTHY scoreboard gate passed")
    return h


def run_cmd(args: list[str], timeout: int = 3600) -> int:
    try:
        return subprocess.run(args, cwd=str(ROOT), env=os.environ.copy(), timeout=timeout).returncode
    except Exception as e:
        log(f"cmd error: {e}")
        return -1


def flywheel_loop() -> None:
    global _cycle_n
    log(f"smart flywheel interval={INTERVAL}s")
    while not _stop.is_set():
        heartbeat()
        _cycle_n += 1
        h = write_healthy_flag()
        log(f"smart cycle #{_cycle_n} start healthy={h.get('healthy')}")
        smart = ROOT / "scripts" / "run_smart_cycle.py"
        if smart.exists():
            code = run_cmd([PY, str(smart)], timeout=2400)
        else:
            code = run_cmd([PY, "-m", "cli.main", "flywheel", "--push"], timeout=2400)
        log(f"smart cycle exit={code}")

        if RECONCILE_EVERY > 0 and _cycle_n % RECONCILE_EVERY == 0:
            log("tool reconcile")
            run_cmd([PY, str(ROOT / "scripts" / "reconcile_tools.py")], timeout=120)

        if BENCH_EVERY > 0 and _cycle_n % BENCH_EVERY == 0:
            log("fast bench (scoreboard discipline)")
            run_cmd([PY, str(ROOT / "scripts" / "bench.py"), "--fast"], timeout=1800)
            write_healthy_flag()

        if QUIZ_EVERY > 0 and _cycle_n % QUIZ_EVERY == 0:
            log("holdout quiz sample")
            run_cmd([PY, str(ROOT / "scripts" / "quiz.py"), "--limit", "5"], timeout=1800)
            run_cmd([PY, "-c", "from core.scoreboard import write_scoreboard; write_scoreboard()"], timeout=30)
            write_healthy_flag()

        for _ in range(max(60, INTERVAL)):
            if _stop.is_set():
                return
            time.sleep(1)


def batch_loop() -> None:
    log(f"batch interval={BATCH_INTERVAL}s")
    while not _stop.is_set():
        heartbeat()
        code = run_cmd([PY, str(ROOT / "scripts" / "batch_worker.py")], timeout=3600)
        log(f"batch exit={code}")
        for _ in range(max(120, BATCH_INTERVAL)):
            if _stop.is_set():
                return
            time.sleep(1)


def dashboard_loop() -> None:
    log(f"dashboard http://127.0.0.1:{PORT}")
    try:
        import uvicorn

        uvicorn.run("dashboard.app:app", host="127.0.0.1", port=PORT, reload=False, log_level="warning")
    except Exception as e:
        log(f"dashboard error: {e}")


def main() -> int:
    print("=" * 60, flush=True)
    print("  @ETHER DAEMON — scoreboard-gated healthy flag", flush=True)
    print(f"  root={ROOT}", flush=True)
    print("=" * 60, flush=True)
    if not acquire_lock():
        return 2
    heartbeat()
    write_healthy_flag()
    if RUN_DASH:
        threading.Thread(target=dashboard_loop, name="dashboard", daemon=True).start()
        time.sleep(1.5)
    if RUN_FLYWHEEL:
        threading.Thread(target=flywheel_loop, name="flywheel", daemon=True).start()
    if RUN_BATCH:
        threading.Thread(target=batch_loop, name="batch", daemon=True).start()

    def _sig(*_a):
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
    log("exit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
