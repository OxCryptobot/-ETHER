"""Moonshot 18 — GEM energy strip (which gem ran last)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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


def infer_gem(hay: str) -> Optional[str]:
    h = (hay or "").lower()
    if any(x in h for x in ("labradorite", "critique", "plan_wire")):
        return "labradorite"
    if any(x in h for x in ("black-tourmaline", "security", "prompt_guard")):
        return "black-tourmaline"
    if any(x in h for x in ("citrine", "pep8", "ruff", "style_gate")):
        return "citrine"
    if any(x in h for x in ("selenite", "symbol_index", "rag", "context_budget")):
        return "selenite"
    if any(x in h for x in ("amethyst", "memory", "preference", "rlhf")):
        return "amethyst"
    if any(x in h for x in ("grandidierite", "evolve", "evolution")):
        return "grandidierite"
    if any(x in h for x in ("pipeline", "rose-quartz", "live")):
        return "rose-quartz"
    if any(x in h for x in ("pytest", "tool_runtime", "ast", "clear-quartz", "direct")):
        return "clear-quartz"
    return None


def _scan() -> Dict[str, Any]:
    counts = {g: 0 for g in GEMS}
    last: Optional[str] = None
    last_job = None

    cdir = ROOT / "artifacts" / "critiques"
    if cdir.exists():
        files = sorted(cdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[:30]:
            counts["labradorite"] += 1
            if last is None:
                last = "labradorite"
                last_job = p.stem

    lj = ROOT / "artifacts" / "host_agent_last_job.json"
    if lj.exists():
        try:
            data = json.loads(lj.read_text(encoding="utf-8"))
            note = str(data.get("note") or "")
            jid = str(data.get("job_id") or "")
            gem = infer_gem(note + " " + jid)
            if gem:
                counts[gem] = counts.get(gem, 0) + 1
                last = gem
                last_job = data.get("job_id")
        except Exception:
            pass

    return {"counts": counts, "last_gem": last, "last_job": last_job}


def publish() -> Dict[str, Any]:
    scan = _scan()
    active_n = sum(1 for g in GEMS if scan["counts"].get(g, 0) > 0)
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "gems": list(GEMS),
        "counts": scan["counts"],
        "last_gem": scan["last_gem"],
        "last_job": scan["last_job"],
        "active_n": active_n,
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
