#!/usr/bin/env python3
"""List local ollama models via CLI (subprocess only)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit


def main() -> None:
    try:
        p = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=30)
        emit(p.returncode == 0, output=(p.stdout or "").strip(), stderr=(p.stderr or "")[:300])
    except FileNotFoundError:
        emit(False, error="ollama not found")
    except Exception as e:
        emit(False, error=str(e))


if __name__ == "__main__":
    main()
