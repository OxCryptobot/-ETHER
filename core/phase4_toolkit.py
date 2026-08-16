"""Phase 4 — toolkit inventory and quarantine safety surface.

Does not fabricate LLM tools. Does not auto-promote.
ETHER_AUTO_PROMOTE stays treated as off.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase4_toolkit.json"
TOOLS = ROOT / "tools"


def inventory() -> Dict[str, Any]:
    quarantine: List[str] = []
    persistent: List[str] = []
    audit: List[str] = []

    qdir = TOOLS / "quarantine"
    if qdir.exists():
        quarantine = sorted(
            p.name for p in qdir.glob("*.py") if p.name != "__init__.py"
        )
    pdir = TOOLS / "persistent"
    if pdir.exists():
        persistent = sorted(
            p.name for p in pdir.glob("*.py") if p.name != "__init__.py"
        )
    adir = TOOLS / "audit"
    if adir.exists():
        audit = sorted(p.name for p in adir.rglob("*.py"))

    auto = (os.getenv("ETHER_AUTO_PROMOTE") or "0").strip() == "1"
    lib_ok = (TOOLS / "_lib.py").exists()
    fab_ok = (TOOLS / "FABRICATE.md").exists()

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "4",
        "quarantine_n": len(quarantine),
        "persistent_n": len(persistent),
        "audit_n": len(audit),
        "quarantine": quarantine[:40],
        "persistent": persistent[:40],
        "lib_ok": lib_ok,
        "fabricate_doc_ok": fab_ok,
        "auto_promote": auto,
        "auto_promote_must_be_off": True,
        "ok": lib_ok and fab_ok and auto is False,
        "note": "New tools must land in quarantine first. Auto-promote default OFF.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2))
