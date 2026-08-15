"""Moonshot 18 — GEM energy strip (which gem ran last)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "gem_energy.json"

GEMS = (
    "clear-quartz",
    "rose-quartz",
    "citrine",
    "selenite",
    "amethyst",
    "black-tourmaline",
    "labradorite",
    "grandidierite",
)


def _scan() -> Dict[str, int]:
    counts = {g: 0 for g in GEMS}
    last: Optional[str] = None
    last_job = None
    # critiques → labradorite
    cdir = ROOT / "artifacts" / "critiques"
    if cdir.exists():
        files = sorted(cdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[:30]:
            counts["labradorite"] += 1
            if last is None:
                last = "labradorite"
                last_job = p.stem
    # last job note heuristics
    lj = ROOT / "artifacts" / "host_agent_last_job.json"
    if lj.exists():
        try:
            data = json.loads(lj.read_text(encoding="utf-8"))
            note = str(data.get("note") or "").lower()
            jid = str(data.get("job_id") or "").lower()
            hay = note + " " + jid
            if "labradorite" in hay or "critique" in hay:
                last = "labradorite"
            elif "pytest" in hay or "tool_runtime" in hay:
                last = "clear-quartz"
            elif "pipeline" in hay or "live" in hay:
                last = "rose-quartz"
            last_job = data.get("job_id")
        except Exception:
            pass
    return {"counts": counts, "last_gem": last, "last_job": last_job}


def publish() -> Dict[str, Any]:
    scan = _scan()
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "gems": list(GEMS),
        "counts": scan["counts"],
        "last_gem": scan["last_gem"],
        "last_job": scan["last_job"],
        "strip": [
            {"gem": g, "n": scan["counts"].get(g, 0), "active": g == scan["last_gem"]}
            for g in GEMS
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
