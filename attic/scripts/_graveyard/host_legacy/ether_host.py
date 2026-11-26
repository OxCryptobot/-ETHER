#!/usr/bin/env python3
"""ETHER Host — headless writer: job agent + foreman. No local Control Matrix.

Face is the Grok Matrix. :8787 is health/API only and must not open a browser.
"""
from __future__ import annotations

import hashlib
import importlib
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

PORT = int(os.environ.get("ETHER_DASH_PORT") or "8787")
# Product face is the Grok Matrix. Never auto-open the retired local UI.
OPEN_BROWSER = (os.environ.get("ETHER_OPEN_BROWSER") or "0").strip() == "1"
SERVE_LOCAL_API = (os.environ.get("ETHER_LOCAL_API") or "1").strip() != "0"

_WATCHED = (
    "scripts/host_agent.py",
    "scripts/ether_host.py",
    "scripts/foreman.py",
    "dashboard/app.py",
)

try:
    from core.dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass


def _file_digest(rel: str) -> str:
    p = ROOT / rel
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except Exception:
        return "missing"


def _snapshot() -> dict:
    return {rel: _file_digest(rel) for rel in _WATCHED}


def _port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _dashboard_healthy(port: int = PORT, timeout: float = 1.5) -> bool:
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
                    ["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5
                )
                print(f"local-api: killed pid={pid} holding :{port}", flush=True)
            except Exception as e:
                print(f"local-api: taskkill pid={pid} failed: {e}", flush=True)
        if pids:
            time.sleep(0.8)
    except Exception as e:
        print(f"local-api: force_free non-fatal: {e}", flush=True)


def _run_uvicorn(port: int) -> None:
    import uvicorn

    uvicorn.run(
        "dashboard.app:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        reload=False,
        access_log=False,
    )


def _start_dashboard() -> None:
    if not SERVE_LOCAL_API:
        print("local-api: disabled (ETHER_LOCAL_API=0)", flush=True)
        return
    if _dashboard_healthy(PORT):
        print(f"local-api: health ok on :{PORT} — reusing (HTML retired)", flush=True)
        return
    if _port_listening(PORT):
        print(f"local-api: :{PORT} listening but NOT healthy — force free + rebind", flush=True)
        _force_free_port(PORT)
    for attempt in range(1, 4):
        try:
            print(f"local-api: starting headless uvicorn on :{PORT} (attempt {attempt})", flush=True)
            _run_uvicorn(PORT)
            print("local-api: uvicorn exited", flush=True)
            return
        except OSError as e:
            print(f"local-api: bind failed attempt {attempt}: {e}", flush=True)
            _force_free_port(PORT)
            time.sleep(0.6 * attempt)
        except Exception as e:
            print(f"local-api error: {e}", flush=True)
            traceback.print_exc()
            time.sleep(1.0)
    print("local-api: FAILED to bind after retries — writer still runs", flush=True)


def _wait_dashboard(timeout_s: float = 8.0) -> bool:
    if not SERVE_LOCAL_API:
        return True
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _dashboard_healthy(PORT):
            return True
        time.sleep(0.35)
    return _dashboard_healthy(PORT)


def _reload_foreman():
    import scripts.foreman as foreman_mod

    return importlib.reload(foreman_mod)


def _hygiene_log() -> None:
    log_path = ROOT / "artifacts" / "host_agent_log.txt"
    try:
        if log_path.exists() and log_path.stat().st_size > 4 * 1024 * 1024:
            bak = log_path.with_suffix(".txt.prev")
            if bak.exists():
                bak.unlink()
            log_path.rename(bak)
            print(f"boot: rotated host_agent_log ({log_path.name})", flush=True)
    except Exception as e:
        print(f"boot: log hygiene non-fatal: {e}", flush=True)


def main() -> int:
    print("=" * 56, flush=True)
    print("  ETHER HOST — headless writer", flush=True)
    print("  FACE   Grok Control Matrix (not :8787)", flush=True)
    print(f"  root   {ROOT}", flush=True)
    print("  Ctrl+C stop", flush=True)
    print("=" * 56, flush=True)

    _hygiene_log()
    try:
        from scripts.live_host import consume, start_ollama

        up = start_ollama()
        consume({"cmd": "attach"})
        print(f"ollama boot up={up}", flush=True)
    except Exception as exc:
        print(f"ollama boot non-fatal: {type(exc).__name__}: {exc}", flush=True)
    boot_snap = _snapshot()
    print(f"boot source snap (minimal watch): {boot_snap}", flush=True)

    t = threading.Thread(target=_start_dashboard, name="local-api", daemon=True)
    t.start()

    ok = _wait_dashboard(10.0)
    if ok:
        print("local-api: HEALTHY (HTML retired, do not open browser)", flush=True)
    else:
        print(f"local-api: NOT HEALTHY after 10s — writer continues", flush=True)

    if OPEN_BROWSER:
        print("ETHER_OPEN_BROWSER=1 ignored for retired UI", flush=True)

    try:
        import scripts.host_agent as agent
    except Exception as e:
        print(f"FATAL import: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return 1

    agent.log("startup: skip nuclear clean_slate (launcher already did it)")
    agent.PENDING.mkdir(parents=True, exist_ok=True)
    agent.DONE.mkdir(parents=True, exist_ok=True)
    agent.FAILED.mkdir(parents=True, exist_ok=True)
    boot_snap = _snapshot()

    try:
        agent.write_status(current_job=None, phase="starting")
    except Exception:
        pass

    try:
        from core.chat_bridge import get_pending_grok

        get_pending_grok()
    except Exception:
        pass

    try:
        foreman = _reload_foreman()
        fr = foreman.tick()
        agent.log(f"foreman boot: {fr}")
    except Exception as e:
        agent.log(f"foreman boot failed (non-fatal): {e}")

    try:
        agent.maybe_auto_rate_climb(force=False)
    except Exception as e:
        agent.log(f"boot auto_rate_climb: {type(e).__name__}: {e}")

    try:
        agent._last_liveness_push = 0.0  # type: ignore[attr-defined]
        agent.push_liveness("startup")
    except Exception as e:
        agent.log(f"startup liveness failed: {e}")

    dash_ok = _dashboard_healthy(PORT) if SERVE_LOCAL_API else False
    print(
        f"BOOT OK — writer live dash={'API' if dash_ok else 'OFF'} face=grok_matrix",
        flush=True,
    )

    while True:
        try:
            agent.write_status(current_job=None, phase="polling")
            agent.git_sync()

            now_snap = _snapshot()
            if now_snap != boot_snap:
                changed = [k for k in _WATCHED if now_snap.get(k) != boot_snap.get(k)]
                agent.log(f"SOURCE UPDATED {changed} — exit 42 for launcher reload")
                agent.write_status(phase="reload", changed=changed)
                return 42

            try:
                agent.maybe_push_chat_bus()
            except Exception as e:
                agent.log(f"chat_bus: {type(e).__name__}: {e}")

            try:
                foreman = _reload_foreman()
                fr = foreman.tick()
                if fr.get("enqueued") or fr.get("playbook") or fr.get("rate_climb_status"):
                    agent.log(f"foreman: {fr}")
            except Exception as e:
                agent.log(f"foreman.tick error: {e}")

            jobs = agent.list_pending()
            if not jobs:
                try:
                    agent.maybe_auto_rate_climb()
                except Exception as e:
                    agent.log(f"idle auto_rate_climb: {type(e).__name__}: {e}")
                jobs = agent.list_pending()

            if not jobs:
                agent.log("idle")
                try:
                    agent.maybe_push_chat_bus()
                except Exception:
                    pass
                try:
                    foreman = _reload_foreman()
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
                try:
                    agent.maybe_push_chat_bus()
                except Exception:
                    pass
                now_snap = _snapshot()
                if now_snap != boot_snap:
                    changed = [k for k in _WATCHED if now_snap.get(k) != boot_snap.get(k)]
                    agent.log(f"SOURCE UPDATED {changed} — exit 42 for launcher reload")
                    agent.write_status(phase="reload", changed=changed)
                    return 42
                try:
                    foreman = _reload_foreman()
                    fr = foreman.tick()
                    if fr.get("enqueued") or fr.get("playbook") or fr.get("rate_climb_status"):
                        agent.log(f"foreman: {fr}")
                except Exception as e:
                    agent.log(f"foreman.tick error: {e}")
                if not agent.list_pending():
                    try:
                        agent.maybe_auto_rate_climb()
                    except Exception as e:
                        agent.log(f"post-job auto_rate_climb: {type(e).__name__}: {e}")

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
