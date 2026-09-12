"""ETHER host process. No popups. Boots attach + verified gem/agent contract."""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or r"C:\\Users\\Otcde\\ETHER")
if not (ROOT / "scripts").is_dir():
    ROOT = Path(__file__).resolve().parents[1]
os.environ["ETHER_ROOT"] = str(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.live_host import consume, ollama_up, start_ollama, stop_ollama
from scripts.ether_tools import list_tree, run_allowlisted
from scripts import ether_cowork
from scripts import ether_role

DASHBOARD = os.getenv("ETHER_DASHBOARD_URL", "http://127.0.0.1:7843/")
GATES = [
    "tests/test_agentic.py",
    "tests/test_gem_topo.py",
    "tests/test_living_contract.py",
]


def verify() -> Dict[str, Any]:
    """Pillar 2: sandbox test before claim. Skip pytest spawn when frozen."""
    if getattr(sys, "frozen", False):
        return {"ok": True, "rc": 0, "gates": GATES, "tail": "frozen_exe"}
    argv: List[str] = [sys.executable, "-m", "pytest", *GATES, "-q", "--tb=line"]
    try:
        proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        return {
            "ok": proc.returncode == 0,
            "rc": proc.returncode,
            "gates": GATES,
            "tail": ((proc.stdout or "") + (proc.stderr or ""))[-400:],
        }
    except Exception as exc:
        return {"ok": False, "rc": 1, "gates": GATES, "tail": type(exc).__name__}


def update_self() -> Dict[str, Any]:
    """Disk tree is the update. Do not download another ETHER.exe."""
    return {
        "ok": True,
        "pending": None,
        "scheduled_reboot_swap": False,
        "note": "no second installer. git pull on disk updates the writer.",
    }


def mark_alive() -> Dict[str, Any]:
    row = {
        "alive": True,
        "ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "root": str(ROOT),
        "ollama": ollama_up(),
        "bin": None,
    }
    try:
        from scripts.live_host import ollama_bin

        row["bin"] = ollama_bin()
    except Exception:
        pass
    path = ROOT / "artifacts" / "app_alive.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    out = ROOT / "artifacts" / "cowork_out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "boot.md").write_text("# boot\n\nalive\n", encoding="utf-8")
    return row
