#!/usr/bin/env python3
"""ETHER Host — ONE window: dashboard + job agent + foreman.

  python -m scripts.ether_host
  # or:  .\\scripts\\start_ether_host.ps1

Dashboard thread + host_agent poll loop. No second terminal.

2026-08-22: After git_sync, if critical source files changed vs boot snapshot,
exit 42 so start_ether_host.ps1 reloads the new modules (live_budget,
host_agent, latency_budget, dashboard). Stops the stale-code timeout death spiral.
"""
from __future__ import annotations

import hashlib
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

PORT = int(os.environ.get("ETHER_DASH_PORT") or "8787")
OPEN_BROWSER = (os.environ.get("ETHER_OPEN_BROWSER") or "1").strip() != "0"

# Files whose change must force a full process restart (exit 42)
_WATCHED = (
    "scripts/host_agent.py",
    "scripts/ether_host.py",
    "core/live_budget.py",
    "core/latency_budget.py",
    "core/job_class.py",
    "core/eligible_rates.py",
    "core/phase1_gate.py",
    "core/multi_llm.py",
    "core/operator_surface.py",
    "core/chat_bus.py",
    "dashboard/app.py",
    "dashboard/static/agent.html",
    "dashboard/collector_host_agent.py",
)

try:
    from core.dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass


def _file_digest(rel: str) -> str:
    p = ROOT / rel
    try:
        data = p.read_bytes()
        return hashlib.sha256(data).hexdigest()[:16]
    except Exception:
        return "missing"


def _snapshot() -> dict:
    return {rel: _file_digest(rel) for rel in _WATCHED}


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _start_dashboard() -> None:
    if not _port_free(PORT):
        print(f"dashboard: port {PORT} already in use — reusing existing UI", flush=True)
        return
    try:
        import uvicorn

        uvicorn.run(
            "dashboard.app:app",
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
            reload=False,
        )
    except Exception as e:
        print(f"dashboard error: {e}", flush=True)
        traceback.print_exc()


def main() -> int:
    url = f"http://127.0.0.1:{PORT}/"
    print("=" * 56, flush=True)
    print("  ETHER HOST — one window", flush=True)
    print(f"  UI     {url}", flush=True)
    print(f"  root   {ROOT}", flush=True)
    print("  Ctrl+C stop", flush=True)
    print("=" * 56, flush=True)

    boot_snap = _snapshot()
    print(f"boot source snap: {boot_snap}", flush=True)

    t = threading.Thread(target=_start_dashboard, name="dashboard", daemon=True)
    t.start()
    time.sleep(1.2)

    if OPEN_BROWSER:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        from scripts import foreman
        import scripts.host_agent as agent
    except Exception as e:
        print(f"FATAL import: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        try:
            status_path = ROOT / "artifacts" / "host_agent_status.json"
            status_path.parent.mkdir(parents=True, exist_ok=True)
            import json
            from datetime import datetime, timezone

            status_path.write_text(
                json.dumps(
                    {
                        "heartbeat": datetime.now(timezone.utc).isoformat(),
                        "phase": "boot_import_fail",
                        "error": f"{type(e).__name__}: {e}",
                        "root": str(ROOT),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        return 1

    agent.git_reset_to_origin("startup")
    # Re-snapshot after hard reset so we only react to *future* changes
    boot_snap = _snapshot()
    agent.PENDING.mkdir(parents=True, exist_ok=True)
    agent.DONE.mkdir(parents=True, exist_ok=True)
    agent.FAILED.mkdir(parents=True, exist_ok=True)

    try:
        fr = foreman.tick()
        agent.log(f"foreman boot: {fr}")
    except Exception as e:
        agent.log(f"foreman boot failed (non-fatal): {e}")

    try:
        agent._last_liveness_push = 0.0  # type: ignore[attr-defined]
        agent.push_liveness("startup")
    except Exception as e:
        agent.log(f"startup liveness failed: {e}")

    print(f"BOOT OK — UI {url} — poll loop", flush=True)

    while True:
        try:
            agent.write_status(current_job=None, phase="polling")
            agent.git_sync()

            # Source-change watch: if critical files moved under us, exit 42
            # so start_ether_host.ps1 reloads the new modules into a fresh process.
            now_snap = _snapshot()
            if now_snap != boot_snap:
                changed = [k for k in _WATCHED if now_snap.get(k) != boot_snap.get(k)]
                agent.log(f"SOURCE UPDATED {changed} — exit 42 for launcher reload")
                agent.write_status(phase="reload", changed=changed)
                return 42

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
                    agent.write_status(
                        current_job=None, phase="idle", foreman=foreman.status()
                    )
                except Exception:
                    agent.write_status(current_job=None, phase="idle")
                agent.push_liveness("idle")
                time.sleep(max(1, agent.POLL))
                continue

            for job_path in jobs:
                agent.process_job(job_path)
                agent.git_sync()
                # Re-check after each job in case a push landed mid-run
                now_snap = _snapshot()
                if now_snap != boot_snap:
                    changed = [k for k in _WATCHED if now_snap.get(k) != boot_snap.get(k)]
                    agent.log(f"SOURCE UPDATED {changed} — exit 42 for launcher reload")
                    agent.write_status(phase="reload", changed=changed)
                    return 42
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
