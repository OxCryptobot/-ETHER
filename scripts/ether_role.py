"""ETHER role: self-build a local-LLM Cowork desktop."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from scripts.ether_cowork import deliver, run_task, schedule


def _root() -> Path:
    import os
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\Users\Otcde\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]


ROLE = "self_build_cowork"


def tick() -> Dict[str, Any]:
    """One self-build turn: inspect tree, write a plan deliverable, keep a schedule."""
    out = run_task("self-build cowork local LLM")
    plan = (
        "Role: " + ROLE + "\n"
        "Goal: local Cowork clone (folder + tasks + 4B).\n"
        "Last files: " + ", ".join(out.get("files") or [])[:500] + "\n"
        "Deliverable: " + str(out.get("deliverable")) + "\n"
        "ts: " + datetime.now(timezone.utc).isoformat() + "\n"
    )
    doc = deliver("self_build_plan", plan)
    schedule("self-build cowork local LLM", 60)
    stamp = _root() / "artifacts" / "self_build_role.json"
    stamp.parent.mkdir(parents=True, exist_ok=True)
    row = {"role": ROLE, "ok": True, "plan": doc.get("path"), "task": out, "ts": datetime.now(timezone.utc).isoformat()}
    stamp.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
