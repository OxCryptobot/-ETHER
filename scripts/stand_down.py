#!/usr/bin/env python3
"""Exit 78 when medic should stand down (idle + fresh heartbeat). Else 0."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(ROOT))
STATUS = ROOT / "artifacts" / "host_agent_status.json"


def main() -> int:
    from core.loop.medic import medic_stand_down

    if not STATUS.exists():
        print("GO")
        return 0
    try:
        status = json.loads(STATUS.read_text(encoding="utf-8"))
    except Exception:
        print("GO")
        return 0
    if medic_stand_down(status):
        print("STAND_DOWN")
        return 78
    print("GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
