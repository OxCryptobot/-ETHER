#!/usr/bin/env python3
"""ETHER Host - ONE window: dashboard + job agent + foreman.

Simple. No auto-reload. Poll, run, push, repeat.

2026-08-15: idle path pushes liveness every ~60s.
2026-08-15b: bulletproof boot — import failures print full traceback and
still attempt a local status write so the failure is never silent.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
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
    try:
        import uvicorn
        uvicorn.run("dashboard.app:app", host="127.0.0.1", port=8787, log_level="warning", reload=False)
    except Exception as e:
        print(f"dashboard error: {e}", flush=True)
        traceback.print_exc()


def main() -> int:
    print("=" * 60, flush=True)
    print("  ETHER HOST - single window", flush=True)
    print("  dashboard  http://127.0.0.1:8787/agent", flush=True)
    print(f"  root={ROOT}", flush=True)
    print("=" * 60, flush=True)

    t = threading.Thread(target=_start_dashboard, name="dashboard", daemon=True)
    t.start()
    time.sleep(1.0)

    try:
        from scripts import foreman
        import scripts.host_agent as agent
    except Exception as e:
        print(f"FATAL import: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        # Still write a local status so local diagnostics exist
        try:
            status_path = ROOT / "artifacts" / "host_agent_status.json"
            status_path.parent.mkdir(parents=True, exist_ok=True)
            import json
            from datetime import datetime, timezone
            status_path.write_text(json.dumps({
                "heartbeat": datetime.now(timezone.utc).isoformat(),
                "phase": "boot_import_fail",
                "error": f"{type(e).__name__}: {e}",
                "root": str(ROOT),
            }, indent=2), encoding="utf-8")
        except Exception:
            pass
        return 1

    agent.git_reset_to_origin("startup")
    agent.PENDING.mkdir(parents=True, exist_ok=True)
    agent.DONE.mkdir(parents=True, exist_ok=True)
    agent.FAILED.mkdir(parents=True, exist_ok=True)

    try:
        fr = foreman.tick()
        agent.log(f"foreman boot: {fr}")
    except Exception as e:
        agent.log(f"foreman boot failed (non-fatal): {e}")
        traceback.print_exc()

    # Forced first liveness — never skip, ignore throttle
    try:
        agent._last_liveness_push = 0.0  # type: ignore[attr-defined]
        agent.push_liveness("startup")
    except Exception as e:
        agent.log(f"startup liveness failed: {e}")
        traceback.print_exc()

    print("BOOT OK — entering poll loop", flush=True)

    while True:
        try:
            agent.write_status(current_job=None, phase="polling")
            agent.git_sync()

            try:
                fr = foreman.tick()
                if fr.get("enqueued") or fr.get("playbook"):
                    agent.log(f"foreman: {fr}")
            except Exception as e:
                agent.log(f"foreman.tick error: {e}")

            jobs = agent.list_pending()
            if not jobs:
                agent.log("idle")
                try:
                    agent.write_status(current_job=None, phase="idle", foreman=foreman.status())
                except Exception:
                    agent.write_status(current_job=None, phase="idle")
                agent.push_liveness("idle")
                time.sleep(max(1, agent.POLL))
                continue

            for job_path in jobs:
                agent.process_job(job_path)
                agent.git_sync()
                try:
                    fr = foreman.tick()
                    if fr.get("enqueued") or fr.get("playbook"):
                        agent.log(f"foreman: {fr}")
                except Exception as e:
                    agent.log(f"foreman.tick error: {e}")

        except KeyboardInterrupt:
            agent.log("stop")
            agent.write_status(phase="stopped")
            return 0
        except Exception as e:
            agent.log(f"loop error: {e}")
            traceback.print_exc()
            try:
                agent.git_sync()
            except Exception:
                pass
            time.sleep(max(1, agent.POLL))


if __name__ == "__main__":
    raise SystemExit(main())
