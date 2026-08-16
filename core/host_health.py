"""Local host health — Phase 1 critical: truth without git push.

Reads artifacts/host_agent_status.json only. Never touches network/git.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
STATUS = ROOT / "artifacts" / "host_agent_status.json"
LAST = ROOT / "artifacts" / "host_agent_last_job.json"
OUT = ROOT / "artifacts" / "host_health.json"
STALE_S = float(os.getenv("ETHER_HOST_STALE_S", "120"))


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute() -> Dict[str, Any]:
    st = _load(STATUS)
    last = _load(LAST)
    hb = st.get("heartbeat")
    age_s: Optional[float] = None
    if hb:
        try:
            t = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
            age_s = round((datetime.now(timezone.utc) - t).total_seconds(), 1)
        except Exception:
            age_s = None

    alive = age_s is not None and age_s <= STALE_S
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "ok": alive,
        "alive": alive,
        "heartbeat": hb,
        "age_s": age_s,
        "stale_after_s": STALE_S,
        "phase": st.get("phase"),
        "current_job": st.get("current_job"),
        "last_job": st.get("last_job") or last.get("job_id"),
        "last_ok": st.get("last_ok", last.get("ok")),
        "root": st.get("root"),
        "git_required": False,
        "note": "Local filesystem heartbeat only — independent of git push",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
