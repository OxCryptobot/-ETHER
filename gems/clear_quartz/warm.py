"""Optional long-lived Docker worker for lower sandbox latency."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Optional
from uuid import uuid4

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
            # Mirror the hardening _run_docker applies. This container was
            # created with none of it — root, writable rootfs, full default
            # capabilities — while being the path that actually executes
            # model-authored code when ETHER_WARM_SANDBOX=1.
            "--network",
            "none",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--pids-limit",
            "128",
            "--user",
            "65534:65534",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--env",
            "HOME=/tmp",
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
    # The container is long-lived, so its writable /tmp is SHARED between
    # programs. Verified attack: one program wrote sitecustomize.py into the
    # user-site path derived from HOME, and a later, unrelated program executed
    # it before its own first line — arbitrary code execution able to silently
    # flip a pass/fail verdict.
    #
    # Two mitigations, both required:
    #   -I  isolated mode: no user site-packages (kills the sitecustomize and
    #       module-shadowing vectors), ignores PYTHON* env vars, and does not
    #       prepend '' to sys.path.
    #   a per-execution HOME, so anything keyed off HOME cannot be pre-planted
    #       by an earlier run.
    #
    # This does not make the shared tmpfs *private* — programs can still read
    # and write each other's leftover files under /tmp. It only removes the
    # paths by which that turns into code execution. If you need true per-run
    # isolation, use the default (non-warm) backend: it costs ~168ms per
    # program, which is under 1% of a run dominated by model latency.
    run_home = f"/tmp/ether-run-{uuid4().hex}"
    try:
        return subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "--env",
                f"HOME={run_home}",
                CONTAINER,
                "python",
                "-I",
                "-",
            ],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return None
