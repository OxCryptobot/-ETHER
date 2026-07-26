"""Infrastructure liveness for Control Matrix notifications."""

from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _hb_age_s(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        try:
            return (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime)
        except Exception:
            return None


def _pid_alive(pid_path: Path) -> bool:
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except Exception:
        return False
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
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


def collect_infra() -> Dict[str, Any]:
    port = int(os.getenv("ETHER_DASH_PORT", "8787"))
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_port = 11434
    try:
        if ":" in ollama_base.split("//", 1)[-1]:
            ollama_port = int(ollama_base.rstrip("/").split(":")[-1].split("/")[0])
    except Exception:
        pass

    daemon_hb = _hb_age_s(ROOT / "memory" / "daemon" / "heartbeat.txt")
    fly_hb = _hb_age_s(ROOT / "memory" / "flywheel" / "heartbeat.txt")
    daemon_pid_ok = _pid_alive(ROOT / "memory" / "daemon" / "daemon.pid")
    dash_up = _port_open("127.0.0.1", port)
    ollama_up = _port_open("127.0.0.1", ollama_port)

    model_info: Dict[str, Any] = {}
    try:
        from core.model_select import select_primary_model

        model_info = select_primary_model()
    except Exception as e:
        model_info = {"error": str(e)[:120]}

    # Runner: process name heuristic (Listener) + last ensure log
    runner_listener = False
    try:
        if os.name == "nt":
            import subprocess

            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Runner.Listener.exe"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            runner_listener = "Runner.Listener.exe" in (r.stdout or "")
    except Exception:
        pass

    alerts: List[Dict[str, str]] = []
    if not daemon_pid_ok:
        alerts.append({"level": "bad", "text": "Daemon process down"})
    elif daemon_hb is None or daemon_hb > 180:
        alerts.append({"level": "bad", "text": f"Daemon heartbeat stale ({daemon_hb}s)"})
    else:
        alerts.append({"level": "ok", "text": "Daemon alive"})

    if not dash_up:
        alerts.append({"level": "bad", "text": f"Control Matrix port {port} closed"})
    else:
        alerts.append({"level": "ok", "text": f"Control Matrix :{port} up"})

    if not ollama_up:
        alerts.append({"level": "bad", "text": "Ollama port closed"})
    else:
        alerts.append({"level": "ok", "text": f"Model {model_info.get('model', '?')}"})

    if not runner_listener:
        alerts.append({"level": "warn", "text": "GitHub runner Listener not detected — install service"})
    else:
        alerts.append({"level": "ok", "text": "GitHub runner Listener up"})

    if fly_hb is None:
        alerts.append({"level": "warn", "text": "No flywheel cycle yet"})
    elif fly_hb > 3600:
        alerts.append({"level": "warn", "text": f"Last flywheel cycle {int(fly_hb)}s ago"})

    overall = "ok"
    if any(a["level"] == "bad" for a in alerts):
        overall = "down"
    elif any(a["level"] == "warn" for a in alerts):
        overall = "degraded"

    return {
        "overall": overall,
        "alerts": alerts,
        "daemon": {
            "pid_alive": daemon_pid_ok,
            "heartbeat_age_s": daemon_hb,
            "ok": daemon_pid_ok and daemon_hb is not None and daemon_hb <= 180,
        },
        "dashboard": {"port": port, "up": dash_up},
        "ollama": {"up": ollama_up, "model": model_info.get("model"), "select": model_info},
        "runner": {"listener": runner_listener},
        "flywheel_heartbeat_age_s": fly_hb,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
