"""Phase 1 → Phase 2 gate status.

GO only when:
  - timeout_rate_eligible < 0.25 (with live_eligible_n > 0)
  - honest_rate_eligible >= 0.99 (with live_eligible_n > 0)
  - soft_launch still blocked until human flags (reported, not flipped here)

Never lifts wheels. Never sets ETHER_SOFT_LAUNCH.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase1_gate.json"
TARGET_TIMEOUT = 0.25
TARGET_HONEST = 0.99
MIN_ELIGIBLE_N = int(os.getenv("ETHER_GATE_MIN_ELIGIBLE_N", "5"))


def compute() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    try:
        from core.eligible_rates import compute as elig_compute

        elig = elig_compute()
    except Exception as e:
        elig = {"error": str(e)[:160]}

    to_e = elig.get("timeout_rate_eligible")
    ho_e = elig.get("honest_rate_eligible")
    n_e = int(elig.get("live_eligible_n") or 0)

    checks.append(
        {
            "id": "eligible_sample_size",
            "ok": n_e >= MIN_ELIGIBLE_N,
            "detail": f"live_eligible_n={n_e} min={MIN_ELIGIBLE_N}",
        }
    )
    checks.append(
        {
            "id": "timeout_rate_eligible",
            "ok": to_e is not None and to_e < TARGET_TIMEOUT and n_e > 0,
            "detail": f"rate={to_e} target<{TARGET_TIMEOUT}",
        }
    )
    checks.append(
        {
            "id": "honest_rate_eligible",
            "ok": ho_e is not None and ho_e >= TARGET_HONEST and n_e > 0,
            "detail": f"rate={ho_e} target>={TARGET_HONEST}",
        }
    )

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    checks.append(
        {
            "id": "wheels_still_on_expected",
            "ok": True,  # informational — ON is correct until gate passes
            "detail": f"training_wheels={wheels}",
        }
    )

    # soft launch must remain blocked by soft_launch module; we only report
    try:
        from core.soft_launch import evaluate

        soft = evaluate()
        checks.append(
            {
                "id": "soft_launch_module_blocked",
                "ok": bool(soft.get("soft_launch_blocked")),
                "detail": str(soft.get("blocked_reasons") or [])[:120],
            }
        )
    except Exception as e:
        soft = {}
        checks.append(
            {"id": "soft_launch_module_blocked", "ok": False, "detail": str(e)[:80]}
        )

    metric_ok = all(
        c["ok"]
        for c in checks
        if c["id"]
        in ("eligible_sample_size", "timeout_rate_eligible", "honest_rate_eligible")
    )
    # Gate to Phase 2 architecture work is metric_ok; soft launch is separate human step
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase_gate": "1_to_2",
        "metrics_go": metric_ok,
        "status": "GO" if metric_ok else "NO_GO",
        "checks": checks,
        "checks_ok": sum(1 for c in checks if c["ok"]),
        "checks_n": len(checks),
        "timeout_rate_eligible": to_e,
        "honest_rate_eligible": ho_e,
        "live_eligible_n": n_e,
        "timeout_rate_raw": elig.get("timeout_rate_raw"),
        "training_wheels": wheels,
        "soft_launch_ready": bool(soft.get("soft_launch_ready")),
        "note": (
            "metrics_go unlocks Phase 2 architecture work only. "
            "Soft launch still needs wheels off + ETHER_SOFT_LAUNCH=1 by human."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
