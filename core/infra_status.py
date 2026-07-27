"""Infrastructure liveness for Control Matrix notifications."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _host_port(url: str, default_host: str, default_port: int) -> Tuple[str, int]:
    """Split a base URL into (host, port).

    The Ollama probe used to keep only the port and always dial 127.0.0.1, so
    an OLLAMA_BASE_URL pointing at another machine was reported "up" whenever
    *some* local process happened to hold that port.
    """
    raw = (url or "").strip()
    if not raw:
        return default_host, default_port
    if "//" not in raw:
        raw = "//" + raw
    try:
        parts = urlsplit(raw, scheme="http")
        host = parts.hostname or default_host
        port = parts.port
        if port is None:
            port = 443 if parts.scheme == "https" else default_port
        return host, int(port)
    except (ValueError, TypeError):
        return default_host, default_port


def _runner_listener_up() -> bool:
    """Is a GitHub Actions self-hosted runner Listener process running?

    This probe lived inside `if os.name == "nt"` and so was hard-False on
    every Linux box, producing an unconditional warn that made `overall` == ok
    unreachable — a permanent false alarm that trains operators to ignore the
    panel.
    """
    try:
        if os.name == "nt":
            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Runner.Listener.exe"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return "Runner.Listener.exe" in (r.stdout or "")
        if shutil.which("pgrep"):
            r = subprocess.run(
                ["pgrep", "-f", "Runner.Listener"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0 and (r.stdout or "").strip():
                return True
            if r.returncode in (0, 1):
                return False
        # /proc fallback for containers without pgrep
        for proc in Path("/proc").glob("[0-9]*"):
            try:
                cmd = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                    "utf-8", "ignore"
                )
            except OSError:
                continue
            if "Runner.Listener" in cmd:
                return True
    except Exception:
        pass
    return False


def _runner_expected() -> bool:
    """Only alert about a missing runner where one is actually meant to exist."""
    if (os.getenv("ETHER_GITHUB_RUNNER", "") or "").strip() in ("1", "true", "yes"):
        return True
    explicit = (os.getenv("ETHER_RUNNER_DIR", "") or "").strip()
    if explicit and Path(explicit).exists():
        return True
    for candidate in (ROOT / "actions-runner", Path.home() / "actions-runner"):
        try:
            if candidate.exists():
                return True
        except OSError:
            continue
    return False


def _docker_probe() -> Dict[str, Any]:
    """Docker CLI + daemon reachability (there was no Docker probe at all).

    ETHER_SANDBOX_BACKEND=docker fails closed, so a dead daemon means every
    sandboxed execution stops — a hard dependency the status panel never
    mentioned.
    """
    out: Dict[str, Any] = {
        "cli": shutil.which("docker") is not None,
        "daemon": False,
        "endpoint": "",
    }
    host = (os.getenv("DOCKER_HOST", "") or "").strip()
    try:
        if host.startswith(("tcp://", "http://", "https://")):
            h, p = _host_port(host, "127.0.0.1", 2375)
            out["endpoint"] = f"{h}:{p}"
            out["daemon"] = _port_open(h, p)
            return out
        sock_path = host[len("unix://"):] if host.startswith("unix://") else "/var/run/docker.sock"
        if os.name == "nt":
            out["endpoint"] = host or "npipe"
            if out["cli"]:
                r = subprocess.run(
                    ["docker", "info", "--format", "{{.ServerVersion}}"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                out["daemon"] = r.returncode == 0
            return out
        out["endpoint"] = sock_path
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.4)
        try:
            s.connect(sock_path)
            out["daemon"] = True
        finally:
            s.close()
    except Exception as e:
        out["error"] = str(e)[:120]
    return out


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
    try:
        port = int(os.getenv("ETHER_DASH_PORT", "8787"))
    except ValueError:
        port = 8787
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_host, ollama_port = _host_port(ollama_base, "127.0.0.1", 11434)
    qdrant_base = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_host, qdrant_port = _host_port(qdrant_base, "127.0.0.1", 6333)
    sandbox_backend = (os.getenv("ETHER_SANDBOX_BACKEND") or "auto").strip().lower()

    daemon_hb = _hb_age_s(ROOT / "memory" / "daemon" / "heartbeat.txt")
    fly_hb = _hb_age_s(ROOT / "memory" / "flywheel" / "heartbeat.txt")
    daemon_pid_ok = _pid_alive(ROOT / "memory" / "daemon" / "daemon.pid")
    dash_up = _port_open("127.0.0.1", port)
    ollama_up = _port_open(ollama_host, ollama_port)
    qdrant_up = _port_open(qdrant_host, qdrant_port)
    docker = _docker_probe()

    model_info: Dict[str, Any] = {}
    try:
        from core.model_select import select_primary_model

        model_info = select_primary_model()
    except Exception as e:
        model_info = {"error": str(e)[:120]}

    # Runner: process name heuristic (Listener), on every platform
    runner_listener = _runner_listener_up()
    runner_expected = _runner_expected()

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
        alerts.append(
            {"level": "bad", "text": f"Ollama unreachable at {ollama_host}:{ollama_port}"}
        )
    else:
        alerts.append({"level": "ok", "text": f"Model {model_info.get('model', '?')}"})

    if sandbox_backend == "docker" and not docker["daemon"]:
        alerts.append({"level": "bad", "text": "Docker daemon down — sandbox fails closed"})
    elif sandbox_backend in ("local", "subprocess", "native"):
        alerts.append({"level": "ok", "text": "Sandbox backend local (Docker not required)"})
    elif not docker["daemon"]:
        alerts.append(
            {"level": "warn", "text": "Docker daemon down — sandbox degrades to host python"}
        )
    else:
        alerts.append({"level": "ok", "text": "Docker daemon up"})

    if not qdrant_up:
        alerts.append(
            {
                "level": "warn",
                "text": f"Qdrant unreachable at {qdrant_host}:{qdrant_port} — memory layer off",
            }
        )
    else:
        alerts.append({"level": "ok", "text": f"Qdrant :{qdrant_port} up"})

    if runner_listener:
        alerts.append({"level": "ok", "text": "GitHub runner Listener up"})
    elif runner_expected:
        alerts.append(
            {"level": "warn", "text": "GitHub runner Listener not detected — install service"}
        )
    else:
        alerts.append({"level": "ok", "text": "GitHub runner not configured (optional)"})

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
        "ollama": {
            "up": ollama_up,
            "host": ollama_host,
            "port": ollama_port,
            "base_url": ollama_base,
            "model": model_info.get("model"),
            "select": model_info,
        },
        "docker": {
            "cli": docker["cli"],
            "daemon": docker["daemon"],
            "endpoint": docker.get("endpoint", ""),
            "required": sandbox_backend == "docker",
            "ok": docker["daemon"] or sandbox_backend in ("local", "subprocess", "native"),
        },
        "qdrant": {
            "up": qdrant_up,
            "host": qdrant_host,
            "port": qdrant_port,
            "url": qdrant_base,
        },
        "runner": {"listener": runner_listener, "expected": runner_expected},
        "flywheel_heartbeat_age_s": fly_hb,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
