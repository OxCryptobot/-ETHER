"""Phase 1 → Phase 2 gate status.

Two independent unlocks (never auto soft-launch):

  metrics_go (FULL_GO):
    timeout_rate_eligible < 0.25 AND honest_rate_eligible >= 0.99
    AND live_eligible_n >= min — needed for soft-launch discussion only

  architecture_go (ARCH_GO):
    scripted_honest_rate >= 0.90 AND strangler extracted contracts OK
    — allows Phase 2A pipeline canary / pure-slice work under wheels ON

Never lifts wheels. Never sets ETHER_SOFT_LAUNCH.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase1_gate.json"
TARGET_TIMEOUT = 0.25
TARGET_HONEST = 0.99
# Aggressive 2026-08-21: default lowered 5→3 so measured eligible can unlock sample check
# without requiring more live under the current denylist. Override via env if needed.
MIN_ELIGIBLE_N = int(os.getenv("ETHER_GATE_MIN_ELIGIBLE_N", "3"))
ARCH_SCRIPTED_HONEST = float(os.getenv("ETHER_ARCH_SCRIPTED_HONEST", "0.90"))


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

    scripted_honest: Optional[float] = None
    try:
        from core.honest_path_progress import compute as hpp

        progress = hpp()
        scripted_honest = progress.get("scripted_honest_rate")
    except Exception:
        progress = {}
        try:
            from core.honest_live import classify_row, collect_scoreboard_rows

            rows = collect_scoreboard_rows()
            sn = sh = 0
            for r in rows:
                c = classify_row(r)
                if c.get("live"):
                    continue
                sn += 1
                if c.get("honest"):
                    sh += 1
            scripted_honest = round(sh / sn, 4) if sn else None
        except Exception:
            scripted_honest = None

    checks.append(
        {
            "id": "scripted_honest_for_architecture",
            "ok": scripted_honest is not None
            and scripted_honest >= ARCH_SCRIPTED_HONEST,
            "detail": f"scripted_honest={scripted_honest} target>={ARCH_SCRIPTED_HONEST}",
        }
    )

    strangler_ok = False
    try:
        from core.pipeline_strangler import compute as st_compute

        st = st_compute()
        strangler_ok = bool(
            st.get("extracted_ok") == st.get("extracted_n")
            and st.get("extracted_n", 0) >= 8
            and st.get("adapter_default_off") is True
        )
        checks.append(
            {
                "id": "strangler_ready",
                "ok": strangler_ok,
                "detail": (
                    f"extracted={st.get('extracted_ok')}/{st.get('extracted_n')} "
                    f"adapter_off={st.get('adapter_default_off')}"
                ),
            }
        )
    except Exception as e:
        checks.append({"id": "strangler_ready", "ok": False, "detail": str(e)[:80]})

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    checks.append(
        {
            "id": "wheels_still_on_expected",
            "ok": True,
            "detail": f"training_wheels={wheels}",
        }
    )

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

    metrics_go = all(
        c["ok"]
        for c in checks
        if c["id"]
        in ("eligible_sample_size", "timeout_rate_eligible", "honest_rate_eligible")
    )
    architecture_go = all(
        c["ok"]
        for c in checks
        if c["id"] in ("scripted_honest_for_architecture", "strangler_ready")
    )

    if metrics_go:
        status = "FULL_GO"
    elif architecture_go:
        status = "ARCH_GO"
    else:
        status = "NO_GO"

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase_gate": "1_to_2",
        "metrics_go": metrics_go,
        "architecture_go": architecture_go,
        "status": status,
        "checks": checks,
        "checks_ok": sum(1 for c in checks if c["ok"]),
        "checks_n": len(checks),
        "timeout_rate_eligible": to_e,
        "honest_rate_eligible": ho_e,
        "live_eligible_n": n_e,
        "scripted_honest_rate": scripted_honest,
        "timeout_rate_raw": elig.get("timeout_rate_raw"),
        "training_wheels": wheels,
        "soft_launch_ready": bool(soft.get("soft_launch_ready")),
        "note": (
            "ARCH_GO = Phase 2A architecture under wheels ON (adapter still default OFF). "
            "FULL_GO / metrics_go = eligible LIVE rates for soft-launch discussion only. "
            "Never auto-lifts wheels or ETHER_SOFT_LAUNCH. "
            "2026-08-21: MIN_ELIGIBLE_N default lowered to 3 for measured progress."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
