"""Phase 1D status — single artifact for measured-lift progress.

Does not lift soft launch or training wheels. Measurement only.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase1d_status.json"


def compute() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"id": name, "ok": ok, "detail": detail[:160]})

    try:
        lat = json.loads(
            (ROOT / "artifacts" / "latency_slo.json").read_text(encoding="utf-8")
        )
        add(
            "latency_timeout_split",
            "live_timeout" in lat and "live_completed" in lat,
            f"to_rate={lat.get('live_timeout_rate')} completed_ratio={lat.get('live_over_scripted_p95')}",
        )
    except Exception as e:
        add("latency_timeout_split", False, str(e))

    try:
        lb = json.loads(
            (ROOT / "artifacts" / "live_budget.json").read_text(encoding="utf-8")
        )
        add(
            "live_budget",
            isinstance(lb.get("max_wall_s"), int) and lb["max_wall_s"] <= 120,
            f"max_wall_s={lb.get('max_wall_s')} wheels={lb.get('training_wheels')}",
        )
    except Exception as e:
        add("live_budget", False, str(e))

    try:
        from core.critique_plan_wire import wire_latest

        w = wire_latest()
        add(
            "critique_plan_wire",
            w.get("training_wheels") is True,
            f"n_replanned={w.get('n_replanned')} critiques={w.get('n_critiques')}",
        )
    except Exception as e:
        add("critique_plan_wire", False, str(e))

    try:
        from dashboard.collector_moonshots import collect_moonshots

        m = collect_moonshots()
        ids = {t["id"] for t in m.get("tiles") or []}
        need = {"latency_slo", "live_timeout", "live_budget", "timeout_retire"}
        add("moonshot_1d_tiles", need.issubset(ids), f"tiles={len(ids)}")
    except Exception as e:
        add("moonshot_1d_tiles", False, str(e))

    try:
        from core.timeout_retirement import compute as retire_compute

        r = retire_compute()
        has_plan = isinstance(r.get("actions"), list) and r.get("target_rate") == 0.25
        add(
            "timeout_retirement_plan",
            has_plan,
            f"rate={r.get('timeout_rate')} actions={len(r.get('actions') or [])}",
        )
        proj = r.get("projected") or {}
        add(
            "denylist_projected_under_target",
            bool(proj.get("under_target")),
            f"proj={proj.get('projected_timeout_rate')} rm={proj.get('timeout_removed')}",
        )
    except Exception as e:
        add("timeout_retirement_plan", False, str(e))
        add("denylist_projected_under_target", False, str(e)[:80])

    try:
        soft = json.loads(
            (ROOT / "artifacts" / "soft_launch_status.json").read_text(encoding="utf-8")
        )
        blocked = bool(
            soft.get("soft_launch_blocked") or not soft.get("soft_launch_ready")
        )
        add(
            "soft_launch_still_blocked",
            blocked,
            str(soft.get("blocked_reasons") or soft.get("note") or "")[:120],
        )
    except Exception as e:
        add("soft_launch_still_blocked", True, f"unknown:{e}")

    ok_n = sum(1 for c in checks if c["ok"])
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "1D",
        "name": "Measured lift",
        "status": "PARTIAL" if ok_n < len(checks) else "ADVANCING",
        "checks_ok": ok_n,
        "checks_n": len(checks),
        "checks": checks,
        "training_wheels": True,
        "soft_launch": False,
        "note": (
            "1D advancing. Projected timeout under target via denylist is not "
            "the same as measured live honest rate. Wheels stay ON."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
