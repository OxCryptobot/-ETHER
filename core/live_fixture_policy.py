"""Live fixture policy — retire chronic timeout fixtures from LIVE attempts.

Reads artifacts/timeout_diagnosis.json. Does not enqueue LIVE.
Used when wheels eventually allow live; safe under wheels ON (no-op path).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
DIAG = ROOT / "artifacts" / "timeout_diagnosis.json"
OUT = ROOT / "artifacts" / "live_fixture_policy.json"

# Hard denylist seed — chronic timeout + merge (observe-loop, no write)
SEED_DENY: List[str] = [
    "ledger",
    "pipeline_ledger",
    "ss_pipeline_ledger",
    "lru",
    "topo",
    "intervals",
    "merge",
]

TOP_N = int(os.getenv("ETHER_LIVE_DENY_TOP_N", "8"))
MIN_TIMEOUT_HITS = int(os.getenv("ETHER_LIVE_DENY_MIN_HITS", "1"))


def _load_diag() -> Dict[str, Any]:
    if not DIAG.exists():
        return {}
    try:
        return json.loads(DIAG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def deny_set(*, top_n: Optional[int] = None, min_hits: Optional[int] = None) -> Set[str]:
    top_n = TOP_N if top_n is None else top_n
    min_hits = MIN_TIMEOUT_HITS if min_hits is None else min_hits
    denied: Set[str] = {s.lower() for s in SEED_DENY if s}
    diag = _load_diag()
    for item in (diag.get("top_fixtures") or [])[:top_n]:
        fx = str(item.get("fixture") or "").strip()
        n = int(item.get("n") or 0)
        if fx and n >= min_hits:
            denied.add(fx.lower())
    return denied


def should_skip_live(
    fixture: str = "", *, job: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Return skip decision for a prospective LIVE job."""
    hay = (fixture or "").lower()
    if job:
        hay = " ".join(
            str(job.get(k) or "") for k in ("fixture", "id", "note", "name")
        ).lower()
    denied = deny_set()
    hit = next((d for d in denied if d and d in hay), None)
    return {
        "skip": hit is not None,
        "reason": f"timeout_denylist:{hit}" if hit else "",
        "denied_n": len(denied),
        "fixture": fixture or (job or {}).get("fixture"),
    }


def publish() -> Dict[str, Any]:
    denied = sorted(deny_set())
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "denied": denied,
        "seed": list(SEED_DENY),
        "top_n": TOP_N,
        "min_hits": MIN_TIMEOUT_HITS,
        "diag_rate": _load_diag().get("timeout_rate"),
        "note": "Advisory denylist for LIVE; wheels/gates still control enqueue",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(publish(), indent=2))
