#!/usr/bin/env python3
"""@ETHER single-window desktop runtime.

One process:
  1) auto git update (optional hard reset)
  2) dashboard on :8787
  3) flywheel autonomy loop
  4) live status printed in THIS console

No extra PowerShell windows required.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
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
PORT = int(os.getenv("ETHER_DASH_PORT", "8787"))
INTERVAL = int(os.getenv("ETHER_FLYWHEEL_INTERVAL", "900"))
OPEN_BROWSER = os.getenv("ETHER_OPEN_BROWSER", "1") == "1"

_stop = threading.Event()


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def git_update() -> None:
    log("git: fetch origin…")
    subprocess.run(["git", "fetch", "origin"], cwd=str(ROOT))
    if (ROOT / ".git" / "MERGE_HEAD").exists():
        log("git: aborting stuck merge")
        subprocess.run(["git", "merge", "--abort"], cwd=str(ROOT))
    if os.getenv("ETHER_GIT_RESET_OK", "0") == "1":
        log("git: reset --hard origin/main")
        subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=str(ROOT))
    else:
        subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=str(ROOT))
    # reinstall quietly so new modules load
    log("pip: editable install…")
    subprocess.run(
        [PY, "-m", "pip", "install", "-e", ".[dev]", "-q"],
        cwd=str(ROOT),
    )


def run_dashboard() -> None:
    log(f"dashboard: http://127.0.0.1:{PORT}")
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
        log(f"dashboard error: {e}")


def run_flywheel_loop() -> None:
    # small delay so dashboard binds first
    time.sleep(2)
    from scripts.flywheel import cycle

    log(f"flywheel: autonomous interval={INTERVAL}s push_gated=True")
    while not _stop.is_set():
        try:
            report = cycle(
                do_push=True,
                min_confidence=float(os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7")),
                max_retries=int(os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3")),
                objective=os.getenv(
                    "ETHER_FLYWHEEL_OBJECTIVE",
                    "Write only this Python code with no markdown:\n"
                    "def is_even(n):\n    return n % 2 == 0\n"
                    "print(is_even(4))\nprint(is_even(5))\n",
                ),
                run_doctor=True,
            )
            ok = report.get("ok")
            conf = (report.get("gates") or {}).get("confidence")
            log(
                f"flywheel cycle done ok={ok} conf={conf} "
                f"pull={(report.get('gates') or {}).get('pull_ok')} "
                f"→ dashboard will refresh"
            )
        except Exception as e:
            log(f"flywheel error: {e}")
        # sleep in chunks so Ctrl+C is responsive
        for _ in range(max(30, INTERVAL)):
            if _stop.is_set():
                break
            time.sleep(1)


def main() -> int:
    print("=" * 60, flush=True)
    print("  @ETHER DESKTOP RUNTIME  (single window)", flush=True)
    print("  Dashboard + Flywheel + Auto-update", flush=True)
    print("  Ctrl+C to stop", flush=True)
    print("=" * 60, flush=True)

    try:
        git_update()
    except Exception as e:
        log(f"git update warning: {e}")

    # reload dotenv after pull
    load_dotenv(ROOT / ".env", override=True)

    t_dash = threading.Thread(target=run_dashboard, name="dashboard", daemon=True)
    t_fw = threading.Thread(target=run_flywheel_loop, name="flywheel", daemon=True)
    t_dash.start()
    t_fw.start()

    if OPEN_BROWSER:
        time.sleep(1.5)
        try:
            webbrowser.open(f"http://127.0.0.1:{PORT}")
        except Exception:
            pass

    log("all systems running in this window")
    try:
        while t_dash.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        log("stopping…")
        _stop.set()
        time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
