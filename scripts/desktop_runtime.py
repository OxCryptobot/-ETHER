#!/usr/bin/env python3
"""@ETHER single-window desktop runtime (OneDrive-safe)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

# Prefer ETHER_ROOT from launcher; else this file's repo parent
_env_root = os.environ.get("ETHER_ROOT", "").strip().strip('"')
if _env_root and (Path(_env_root) / "scripts" / "desktop_runtime.py").exists():
    ROOT = Path(_env_root).resolve()
else:
    ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)
os.environ["ETHER_ROOT"] = str(ROOT)

try:
    from core.dotenv import load_dotenv
except Exception:

    def load_dotenv(*_a, **_k):  # type: ignore
        return None


# .env must load BEFORE these setdefault() calls — the loader never overrides
# an already-set variable, so doing it the other way round silently ignored an
# operator's ETHER_FLYWHEEL_PUSH=0 and force-enabled ETHER_GIT_RESET_OK.
load_dotenv(ROOT / ".env")

os.environ.setdefault("ETHER_GIT_RESET_OK", "1")
os.environ.setdefault("ETHER_PULL_SOFT", "1")
# MEAS-005: report pushes are operator opt-in (ETHER_FLYWHEEL_PUSH=1 in .env); default off
os.environ.setdefault("ETHER_FLYWHEEL_PUSH", "0")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")


load_dotenv(ROOT / ".env")

PY = sys.executable
PORT = int(os.getenv("ETHER_DASH_PORT", "8787"))
INTERVAL = int(os.getenv("ETHER_FLYWHEEL_INTERVAL", "900"))
OPEN_BROWSER = os.getenv("ETHER_OPEN_BROWSER", "1") == "1"
SKIP_GIT = os.getenv("ETHER_DESKTOP_SKIP_GIT", "0") == "1"

_stop = threading.Event()


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def pick_port(preferred: int) -> int:
    if port_free(preferred):
        return preferred
    log(f"port {preferred} busy — scanning…")
    for p in range(preferred, preferred + 20):
        if port_free(p):
            log(f"using port {p}")
            return p
    return preferred


def git_update() -> None:
    if SKIP_GIT:
        log("git: skipped")
        return
    log("git: fetch origin…")
    r = subprocess.run(["git", "fetch", "origin"], cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        log(f"git fetch warning: {(r.stderr or r.stdout or '')[:200]}")
    if (ROOT / ".git" / "MERGE_HEAD").exists():
        subprocess.run(["git", "merge", "--abort"], cwd=str(ROOT), capture_output=True)
    if os.getenv("ETHER_GIT_RESET_OK", "0") == "1":
        log("git: reset --hard origin/main")
        subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=str(ROOT), capture_output=True)
    log("pip: editable install…")
    subprocess.run(
        [PY, "-m", "pip", "install", "-e", ".[dev]", "-q"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def run_dashboard(port: int) -> None:
    log(f"dashboard: http://127.0.0.1:{port}")
    try:
        import uvicorn

        uvicorn.run(
            "dashboard.app:app",
            host="127.0.0.1",
            port=port,
            reload=False,
            log_level="warning",
        )
    except Exception as e:
        log(f"dashboard error: {e}")


def run_flywheel_loop() -> None:
    time.sleep(3)
    log(f"flywheel: interval={INTERVAL}s")
    while not _stop.is_set():
        try:
            cmd = [
                PY,
                "-m",
                "cli.main",
                "flywheel",
                "--push",
                "--min-confidence",
                os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7"),
                "--max-retries",
                os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3"),
            ]
            log("flywheel: starting cycle…")
            p = subprocess.run(cmd, cwd=str(ROOT), env=os.environ.copy())
            log(f"flywheel: cycle exit={p.returncode}")
        except Exception as e:
            log(f"flywheel error: {e}")
        for _ in range(max(30, INTERVAL)):
            if _stop.is_set():
                return
            time.sleep(1)


def main() -> int:
    print("=" * 60, flush=True)
    print("  @ETHER DESKTOP RUNTIME", flush=True)
    print(f"  root: {ROOT}", flush=True)
    print(f"  python: {PY}", flush=True)
    print("  Ctrl+C to stop", flush=True)
    print("=" * 60, flush=True)

    if not (ROOT / "scripts" / "desktop_runtime.py").exists():
        log(f"FATAL: desktop_runtime.py missing under {ROOT}")
        return 2

    try:
        git_update()
    except Exception as e:
        log(f"git/pip warning (continuing): {e}")

    load_dotenv(ROOT / ".env", override=True)

    port = pick_port(PORT)
    os.environ["ETHER_DASH_PORT"] = str(port)

    t_dash = threading.Thread(target=run_dashboard, args=(port,), name="dashboard", daemon=True)
    t_fw = threading.Thread(target=run_flywheel_loop, name="flywheel", daemon=True)
    t_dash.start()
    t_fw.start()

    if OPEN_BROWSER:
        time.sleep(2.0)
        url = f"http://127.0.0.1:{port}"
        log(f"opening {url}")
        try:
            webbrowser.open(url)
        except Exception as e:
            log(f"browser: {e}")

    log("running — leave this window open")
    try:
        while t_dash.is_alive():
            time.sleep(1)
        log("dashboard exited")
        return 1
    except KeyboardInterrupt:
        log("stopping…")
        _stop.set()
        time.sleep(1)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
