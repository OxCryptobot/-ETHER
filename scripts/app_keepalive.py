"""Arm hidden logon keepalive from the ETHER app. No operator shell."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict


def ensure_keepalive(root: Path) -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": True, "armed": False, "note": "not_windows"}
    name = "ETHER-keepalive"
    xml = root / "scripts" / "ether_keepalive.xml"
    flags = 0x08000000
    try:
        query = subprocess.run(
            ["schtasks", "/Query", "/TN", name],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=flags,
        )
        created = False
        if query.returncode != 0 and xml.is_file():
            cr = subprocess.run(
                ["schtasks", "/Create", "/TN", name, "/XML", str(xml), "/F"],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=flags,
            )
            created = cr.returncode == 0
        run = subprocess.run(
            ["schtasks", "/Run", "/TN", name],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=flags,
        )
        return {"ok": True, "armed": True, "created": created, "ran": run.returncode == 0}
    except Exception as exc:
        return {"ok": False, "armed": False, "error": type(exc).__name__}
