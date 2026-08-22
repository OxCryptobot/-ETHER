#!/usr/bin/env python3
"""ETHER Host — ONE window: dashboard + job agent + foreman.

  python -m scripts.ether_host
  # or:  .\\scripts\\start_ether_host.ps1

Dashboard thread + host_agent poll loop. No second terminal.

Hard rule: dashboard MUST come up. Never silently skip uvicorn because
the port "looks busy". Probe /api/health; if unhealthy, force-bind.
"""
from __future__ import annotations

import hashlib
import os
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
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


def _port_listening(port: int) -> bool:
    """True if something accepts TCP on 127.0.0.1:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _dashboard_healthy(port: int = PORT, timeout: float = 1.5) -> bool:
    """True only if OUR Control Matrix answers /api/health with ok."""
    url = f"http://127.0.0.1:{port}/api/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            body = resp.read().decode("utf-8", errors="replace")
            return '"ok"' in body and "ether-dashboard" in body
    except Exception:
        return False


def _force_free_port(port: int) -> None:
    """Best-effort: on Windows, kill whatever holds the port."""
    if sys.platform != "win32":
        return
    try:
        import subprocess

        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=8,
            encoding="utf-8",
            errors="replace",
        )
        pids = set()
        needle = f":{port}"
        for line in (out.stdout or "").splitlines():
            if needle not in line:
                continue
            if "LISTENING" not in line.upper() and "ESTABLISHED" not in line.upper():
                continue
            parts = line.split()
            if not parts:
                continue
            pid = parts[-1]
            if pid.isdigit() and int(pid) > 0:
                pids.add(pid)
        for pid in pids:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True,
                    timeout=5,
                )
                print(f"dashboard: killed pid={pid} holding :{port}", flush=True)
            except Exception as e:
                print(f"dashboard: taskkill pid={pid} failed: {e}", flush=True)
        if pids:
            time.sleep(0.8)
    except Exception as e:
        print(f"dashboard: force_free non-fatal: {e}", flush=True)


def _run_uvicorn(port: int) -> None:
    import uvicorn

    # SO_REUSEADDR is default in uvicorn; bind 127.0.0.1 only
    uvicorn.run(
        "dashboard.app:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        reload=False,
        access_log=False,
    )


def _start_dashboard() -> None:
    """Bring Control Matrix up. Never silently skip."""
    if _dashboard_healthy(PORT):
        print(f"dashboard: healthy on :{PORT} — reusing", flush=True)
        return

    if _port_listening(PORT):
        print(
            f"dashboard: :{PORT} listening but NOT healthy — force free + rebind",
            flush=True,
        )
        _force_free_port(PORT)

    for attempt in range(1, 4):
        try:
            print(f"dashboard: starting uvicorn on :{PORT} (attempt {attempt})", flush=True)
            _run_uvicorn(PORT)
            # uvicorn.run blocks; if it returns, server stopped
            print("dashboard: uvicorn exited", flush=True)
            return
        except OSError as e:
            print(f"dashboard: bind failed attempt {attempt}: {e}", flush=True)
            _force_free_port(PORT)
            time.sleep(0.6 * attempt)
        except Exception as e:
            print(f"dashboard error: {e}", flush=True)
            traceback.print_exc()
            time.sleep(1.0)
    print("dashboard: FAILED to bind after retries — UI will be down", flush=True)


def _wait_dashboard(timeout_s: float = 8.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _dashboard_healthy(PORT):
            return True
        time.sleep(0.35)
    return _dashboard_healthy(PORT)


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

    ok = _wait_dashboard(10.0)
    if ok:
        print(f"dashboard: HEALTHY {url}", flush=True)
    else:
        print(
            f"dashboard: NOT HEALTHY after 10s — check port {PORT} / uvicorn logs",
            flush=True,
        )

    if OPEN_BROWSER and ok:
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
                        "dashboard_ok": ok,
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

    # Re-check dashboard after git reset (static files may have changed)
    dash_ok = _dashboard_healthy(PORT)
    print(
        f"BOOT OK — UI {url} dash={'UP' if dash_ok else 'DOWN'} — poll loop",
        flush=True,
    )
    if not dash_ok:
        agent.log("WARNING: dashboard not healthy at boot — operator surface unreachable")

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
