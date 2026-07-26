"""Optional long-lived Docker worker for lower sandbox latency."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Optional

CONTAINER = "ether-cq-warm"
IMAGE = "python:3.12-slim"


def warm_enabled() -> bool:
    return os.getenv("ETHER_WARM_SANDBOX", "0") == "1"


def ensure_warm() -> bool:
    if not warm_enabled():
        return False
    # already running?
    ps = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name=^{CONTAINER}$"],
        capture_output=True,
        text=True,
    )
    if ps.stdout.strip():
        return True
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    r = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            "--network",
            "none",
            "--memory",
            "512m",
            "--cpus",
            "1",
            IMAGE,
            "sleep",
            "infinity",
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def run_in_warm(code: str, timeout: int) -> Optional[subprocess.CompletedProcess]:
    if not ensure_warm():
        return None
    # docker exec -i with python -
    try:
        return subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "python", "-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return None
