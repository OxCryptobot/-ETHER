#!/usr/bin/env python3
"""ETHER Host — ONE window: dashboard + job agent + foreman.

    .\.venv\Scripts\python.exe scripts\ether_host.py

Dashboard: http://127.0.0.1:8787/agent
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

try:
    from core.dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass


def _start_dashboard() -> None:
    import uvicorn

    uvicorn.run("dashboard.app:app", host="127.0.0.1", port=8787, log_level="warning", reload=False)


def main() -> int:
    print("=" * 60, flush=True)
    print("  ETHER HOST — single window", flush=True)
    print("  dashboard  http://127.0.0.1:8787/agent", flush=True)
    print("  agent      job consumer", flush=True)
    print("  foreman    apprentice curriculum", flush=True)
    print("=" * 60, flush=True)

    t = threading.Thread(target=_start_dashboard, name="dashboard", daemon=True)
    t.start()
    time.sleep(1.2)

    # Import agent after path setup; run its main loop with foreman hooks
    from scripts import foreman
    import scripts.host_agent as agent

    # Boot sync
    agent.git_reset_to_origin("ether_host startup")
    agent.PENDING.mkdir(parents=True, exist_ok=True)
    agent.DONE.mkdir(parents=True, exist_ok=True)
    agent.FAILED.mkdir(parents=True, exist_ok=True)

    # Seed queue from curriculum if empty
    fr = foreman.tick()
    agent.log(f"foreman boot: {fr}")

    while True:
        try:
            agent.write_status(current_job=None, phase="polling")
            agent.git_sync()
            # Foreman fills queue when empty
            fr = foreman.tick()
            if fr.get("enqueued") or fr.get("playbook"):
                agent.log(f"foreman: {fr}")

            jobs = agent.list_pending()
            if not jobs:
                agent.log("idle")
                agent.write_status(
                    current_job=None,
                    phase="idle",
                    foreman=foreman.status(),
                )
                time.sleep(max(1, agent.POLL))
                continue

            for job_path in jobs:
                agent.process_job(job_path)
                agent.git_sync()
                fr = foreman.tick()
                if fr.get("enqueued") or fr.get("playbook"):
                    agent.log(f"foreman: {fr}")
        except KeyboardInterrupt:
            agent.log("stop")
            agent.write_status(phase="stopped")
            return 0
        except Exception as e:
            agent.log(f"loop error: {e}")
            try:
                agent.git_sync()
            except Exception:
                pass
            time.sleep(max(1, agent.POLL))


if __name__ == "__main__":
    raise SystemExit(main())
