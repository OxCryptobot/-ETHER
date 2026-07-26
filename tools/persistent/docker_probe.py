#!/usr/bin/env python3
"""Probe docker availability and python:3.12-slim image."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit


def main() -> None:
    try:
        v = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, text=True, timeout=20)
        images = subprocess.run(["docker", "images", "-q", "python:3.12-slim"], capture_output=True, text=True, timeout=20)
        emit(
            True,
            docker_ok=v.returncode == 0,
            server_version=(v.stdout or "").strip(),
            python_slim_present=bool((images.stdout or "").strip()),
        )
    except FileNotFoundError:
        emit(False, error="docker not found")
    except Exception as e:
        emit(False, error=str(e))


if __name__ == "__main__":
    main()
