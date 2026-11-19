"""Retired name. Kept so an old task/shortcut lands in the ONE supervisor.

The single start path is scripts/host_supervisor.py via the ETHER-Host task
(scripts/install_host.cmd). The supervisor's OS lock makes a second copy exit.
"""
from __future__ import annotations

import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.host_supervisor import main, tick  # noqa: E402,F401

if __name__ == "__main__":
    raise SystemExit(main())
