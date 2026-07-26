#!/usr/bin/env python3
"""Check if local ports are open (TCP connect)."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input


def open_port(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> None:
    inp = read_input()
    ports = inp.get("ports") or [11434, 6333, 8787]
    host = inp.get("host") or "127.0.0.1"
    result = {str(p): open_port(int(p), host) for p in ports}
    emit(True, host=host, ports=result)


if __name__ == "__main__":
    main()
