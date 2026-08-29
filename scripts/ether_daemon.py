#!/usr/bin/env python3
"""@ETHER daemon — stand-alone: flywheel + batch + recovery + dashboard + watchdog."""

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
from typing import Callable, Dict, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# .env MUST load first. These are setdefault() calls and core/dotenv.py never
# overrides an already-set variable, so loading .env afterwards left the
# operator's explicit choices silently ignored — a .env with
# ETHER_FLYWHEEL_PUSH=0 still auto-pushed to the shared remote, and
# ETHER_GIT_RESET_OK=1 was force-enabled behind their back.
try:
    from core.dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

os.environ.setdefault("ETHER_GIT_RESET_OK", "1")
os.environ.setdefault("ETHER_PULL_SOFT", "1")
# MEAS-005: report pushes are operator opt-in (ETHER_FLYWHEEL_PUSH=1 in .env); default off
os.environ.setdefault("ETHER_FLYWHEEL_PUSH", "0")
os.environ.setdefault("ETHER_CURRICULUM", "1")
os.environ.setdefault("ETHER_EXPERIENCE", "1")
os.environ.setdefault("ETHER_BENCH_GUARDIAN", "1")
os.environ.setdefault("ETHER_BURST_ON_FAIL", "1")
os.environ.setdefault("ETHER_CURRICULUM_FAIL_RATE", "0.4")
os.environ.setdefault("ETHER_AUTO_ENQUEUE", "1")
os.environ.setdefault("ETHER_GUARDIAN_AUTO_BASELINE", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")

PY = sys.executable
INTERVAL = int(os.getenv("ETHER_DAEMON_INTERVAL", os.getenv("ETHER_FLYWHEEL_INTERVAL", "900")))
BATCH_INTERVAL = int(os.getenv("ETHER_BATCH_INTERVAL", "600"))
BATCH_LIMIT = int(os.getenv("ETHER_BATCH_LIMIT", "2"))
RECONCILE_EVERY = int(os.getenv("ETHER_RECONCILE_EVERY_N", "3"))
BENCH_EVERY = int(os.getenv("ETHER_BENCH_EVERY_N", "4"))
QUIZ_EVERY = int(os.getenv("ETHER_QUIZ_EVERY_N", "6"))
RECOVERY_COOLDOWN = int(os.getenv("ETHER_RECOVERY_COOLDOWN_S", "1800"))
RUN_DASH = os.getenv("ETHER_DAEMON_DASHBOARD", "1") == "1"
RUN_FLYWHEEL = os.getenv("ETHER_DAEMON_FLYWHEEL", "1") == "1"
RUN_BATCH = os.getenv("ETHER_DAEMON_BATCH", "1") == "1"
RUN_CHAT = os.getenv("ETHER_DAEMON_CHAT", "1") == "1"
CHAT_INTERVAL = int(os.getenv("ETHER_CHAT_INTERVAL", "20"))
PORT = int(os.getenv("ETHER_DASH_PORT", "8787"))

PID_PATH = ROOT / "memory" / "daemon" / "daemon.pid"
HB_PATH = ROOT / "memory" / "daemon" / "heartbeat.txt"
LOG_PATH = ROOT / "memory" / "daemon" / "daemon.log"
HEALTH_FLAG = ROOT / "memory" / "daemon" / "healthy.json"
_stop = threading.Event()
_cycle_n = 0
_last_recovery = 0.0
_threads: Dict[str, Optional[threading.Thread]] = {
    "flywheel": None,
    "batch": None,
    "dashboard": None,
    "chat": None,
}


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


def boot_self_test() -> None:
    script = ROOT / "scripts" / "self_test_autonomy.py"
    if not script.exists():
        log("boot self-test skipped (missing)")
        return
    code = run_cmd([PY, str(script)], timeout=120)
    log(f"boot self-test exit={code}")


def maybe_recover(h: dict) -> None:
    global _last_recovery
    if h.get("healthy"):
        return
    now = time.time()
    if now - _last_recovery < RECOVERY_COOLDOWN:
        log(f"recovery cooldown {int(RECOVERY_COOLDOWN - (now - _last_recovery))}s left")
        return
    _last_recovery = now
    log("RECOVERY CYCLE starting (stand-alone self-heal)")
    try:
        from core.autonomy import recovery_cycle

        report = recovery_cycle()
        healthy = (report.get("healthy") or {}).get("healthy")
        log(f"RECOVERY CYCLE done healthy={healthy}")
        write_healthy_flag()
    except Exception as e:
        log(f"RECOVERY error: {e}")


def flywheel_loop() -> None:
    global _cycle_n
    log(f"smart flywheel interval={INTERVAL}s")
    try:
        from core.autonomy import seed_queue_if_empty

        seed_queue_if_empty()
    except Exception as e:
        log(f"seed error: {e}")

    while not _stop.is_set():
        try:
            heartbeat()
            _cycle_n += 1
            h = write_healthy_flag()
            if not h.get("healthy"):
                maybe_recover(h)
                h = write_healthy_flag()

            # declare_healthy() previously gated nothing: the verdict was
            # logged and the cycle ran regardless, so an unhealthy system kept
            # generating, learning and (with push enabled) committing. Skip the
            # cycle instead. _stop.wait() rather than a bare `continue`, since
            # continuing from inside the try skips the loop's trailing sleep
            # and would busy-spin.
            if not h.get("healthy"):
                log(f"GATE: skipping smart cycle — unhealthy: {h.get('reasons')}")
                _stop.wait(max(60, INTERVAL))
                continue

            log(f"smart cycle #{_cycle_n} start healthy={h.get('healthy')}")
            smart = ROOT / "scripts" / "run_smart_cycle.py"
            if smart.exists():
                code = run_cmd([PY, str(smart)], timeout=2400)
            else:
                # Fallback only reachable on a broken install (run_smart_cycle.py
                # missing). The explicit --push is the operator-opt-in exception
                # to MEAS-005's default-off posture; see ADR 0003.
                code = run_cmd([PY, "-m", "cli.main", "flywheel", "--push"], timeout=2400)
            log(f"smart cycle exit={code}")

            if RECONCILE_EVERY > 0 and _cycle_n % RECONCILE_EVERY == 0:
                log("tool reconcile")
                run_cmd([PY, str(ROOT / "scripts" / "reconcile_tools.py")], timeout=120)

            if BENCH_EVERY > 0 and _cycle_n % BENCH_EVERY == 0:
                log("fast bench (scoreboard discipline)")
                run_cmd([PY, str(ROOT / "scripts" / "bench.py"), "--fast"], timeout=1800)
                try:
                    from core.autonomy import maybe_reset_baseline_on_recovery, reevaluate_guardian

                    maybe_reset_baseline_on_recovery()
                    reevaluate_guardian()
                except Exception as e:
                    log(f"guardian post-bench error: {e}")
                write_healthy_flag()

            if QUIZ_EVERY > 0 and _cycle_n % QUIZ_EVERY == 0:
                log("holdout quiz sample")
                run_cmd([PY, str(ROOT / "scripts" / "quiz.py"), "--limit", "5"], timeout=1800)
                run_cmd(
                    [PY, "-c", "from core.scoreboard import write_scoreboard; write_scoreboard()"],
                    timeout=30,
                )
                write_healthy_flag()
        except Exception as e:
            log(f"flywheel loop error (will continue): {e}")

        for _ in range(max(60, INTERVAL)):
            if _stop.is_set():
                return
            time.sleep(1)


def batch_loop() -> None:
    log(f"batch interval={BATCH_INTERVAL}s limit={BATCH_LIMIT}")
    while not _stop.is_set():
        try:
            heartbeat()
            try:
                from core.autonomy import seed_queue_if_empty

                seed_queue_if_empty()
            except Exception:
                pass
            code = run_cmd(
                [PY, str(ROOT / "scripts" / "batch_worker.py"), "--limit", str(max(1, BATCH_LIMIT))],
                timeout=3600,
            )
            log(f"batch exit={code}")
        except Exception as e:
            log(f"batch loop error (will continue): {e}")
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


def chat_loop() -> None:
    """Drain Dual-chat inbox → outbox. Fail-closed. No Ollama unless ETHER_CHAT_LLM=1."""
    script = ROOT / "scripts" / "chat_bus_tick.py"
    log(f"chat bus interval={CHAT_INTERVAL}s script={script.exists()}")
    while not _stop.is_set():
        try:
            heartbeat()
            if script.exists():
                code = run_cmd([PY, str(script)], timeout=90)
                log(f"chat bus tick exit={code}")
            else:
                log("chat bus skipped (missing chat_bus_tick.py)")
        except Exception as e:
            log(f"chat bus error (will continue): {e}")
        for _ in range(max(10, CHAT_INTERVAL)):
            if _stop.is_set():
                return
            time.sleep(1)


def _start_thread(name: str, target: Callable[[], None]) -> None:
    t = threading.Thread(target=target, name=name, daemon=True)
    t.start()
    _threads[name] = t
    log(f"started thread {name}")


def watchdog() -> None:
    """Restart dead worker threads while daemon is alive."""
    while not _stop.is_set():
        time.sleep(30)
        if _stop.is_set():
            return
        mapping = {
            "flywheel": (RUN_FLYWHEEL, flywheel_loop),
            "batch": (RUN_BATCH, batch_loop),
            "dashboard": (RUN_DASH, dashboard_loop),
            "chat": (RUN_CHAT, chat_loop),
        }
        for name, (enabled, fn) in mapping.items():
            if not enabled:
                continue
            t = _threads.get(name)
            if t is None or not t.is_alive():
                log(f"WATCHDOG: restarting dead thread {name}")
                try:
                    _start_thread(name, fn)
                except Exception as e:
                    log(f"WATCHDOG restart failed {name}: {e}")


def main() -> int:
    print("=" * 60, flush=True)
    print("  @ETHER DAEMON — autonomous stand-alone mode", flush=True)
    print(f"  root={ROOT}", flush=True)
    print("  recovery | curriculum | batch | chat bus | guardian | watchdog", flush=True)
    print("=" * 60, flush=Tru