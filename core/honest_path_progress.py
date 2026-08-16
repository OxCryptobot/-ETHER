"""Honest-path progress while training wheels stay ON.

Phase 1 close-out needs two tracks:
  1) eligible LIVE rates (soft-launch / metrics_go)
  2) scripted tool-path rates (architecture readiness signal)

Wheels block new LIVE — progress must still be visible via scripted.
Does not lift gates.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "honest_path_progress.json"


def _rate(n: int, d: int) -> Optional[float]:
    if d <= 0:
        return None
    return round(n / d, 4)


def compute() -> Dict[str, Any]:
    from core.honest_live import classify_row, collect_scoreboard_rows

    rows = collect_scoreboard_rows()
    scripted_n = 0
    scripted_honest = 0
    scripted_ok = 0
    toolish_n = 0
    toolish_honest = 0

    for r in rows:
        c = classify_row(r)
        live = bool(c.get("live"))
        if live:
            continue
        scripted_n += 1
        if c.get("ok"):
            scripted_ok += 1
        if c.get("honest"):
            scripted_honest += 1
        if c.get("toolish") or c.get("honest"):
            toolish_n += 1
            if c.get("honest"):
                toolish_honest += 1

    elig: Dict[str, Any] = {}
    try:
        from core.eligible_rates import compute as elig_compute

        elig = elig_compute()
    except Exception as e:
        elig = {"error": str(e)[:120]}

    gate: Dict[str, Any] = {}
    try:
        from core.phase1_gate import compute as gate_compute

        gate = gate_compute()
    except Exception as e:
        gate = {"error": str(e)[:120]}

    blockers: List[str] = []
    if gate.get("status") == "NO_GO":
        for c in gate.get("checks") or []:
            if not c.get("ok") and c.get("id") != "wheels_still_on_expected":
                blockers.append(f"{c.get('id')}:{c.get('detail')}")
    blockers.append("training_wheels_on")
    blockers.append("prefer_scripted_until_eligible_honest")

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "scripted_n": scripted_n,
        "scripted_ok_n": scripted_ok,
        "scripted_honest_n": scripted_honest,
        "scripted_honest_rate": _rate(scripted_honest, scripted_n),
        "scripted_ok_rate": _rate(scripted_ok, scripted_n),
        "toolish_n": toolish_n,
        "toolish_honest_n": toolish_honest,
        "toolish_honest_rate": _rate(toolish_honest, toolish_n),
        "eligible": {
            "live_eligible_n": elig.get("live_eligible_n"),
            "timeout_rate_eligible": elig.get("timeout_rate_eligible"),
            "honest_rate_eligible": elig.get("honest_rate_eligible"),
            "timeout_rate_raw": elig.get("timeout_rate_raw"),
        },
        "phase1_gate": {
            "status": gate.get("status"),
            "metrics_go": gate.get("metrics_go"),
        },
        "blockers": blockers[:12],
        "wheels_on": True,
        "soft_launch_blocked": True,
        "note": (
            "Under wheels ON, scripted honest/tool rates are the active progress "
            "signal. Eligible LIVE rates gate soft launch; metrics_go gates Phase 2."
        ),
    }
    payload["ok"] = scripted_n > 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
