"""Phase 7 status — north-star system package.

SYSTEM_PACKAGE_COMPLETE when pillars + living checklist + roadmap pass.
Product soft launch remains LOCKED until metrics_go + human flags.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase7_status.json"


def compute() -> Dict[str, Any]:
    packages: List[Dict[str, Any]] = []

    def pkg(pid: str, name: str, ok: bool, detail: str = "") -> None:
        packages.append(
            {"id": pid, "name": name, "ok": bool(ok), "detail": detail[:160]}
        )

    try:
        from core.phase7_pillars import check

        p = check()
        pkg(
            "7-pillars",
            "Three-pillar identity",
            bool(p.get("ok")),
            f"{p.get('pillars_ok')}/{p.get('pillars_n')}",
        )
    except Exception as e:
        pkg("7-pillars", "Three-pillar identity", False, str(e))

    try:
        from core.phase7_living_checklist import checklist

        c = checklist()
        pkg(
            "7-living",
            "Living-agent checklist",
            bool(c.get("ok")) and c.get("autonomous_claim") is False,
            f"ready={c.get('ready_n')} locked={c.get('locked_n')} gaps={c.get('gap_n')}",
        )
    except Exception as e:
        pkg("7-living", "Living-agent checklist", False, str(e))

    try:
        from core.phase7_roadmap import rollup

        r = rollup()
        pkg(
            "7-roadmap",
            "Full roadmap rollup",
            bool(r.get("ok")) and r.get("soft_launch_blocked") is True,
            f"phases={len(r.get('phases') or [])} remaining={len(r.get('remaining_real_work') or [])}",
        )
    except Exception as e:
        pkg("7-roadmap", "Full roadmap rollup", False, str(e))

    try:
        from core.phase6_status import compute as p6

        p6s = p6()
        pkg(
            "7-phase6-prereq",
            "Phase 6 operator prerequisite",
            bool(p6s.get("operator_complete")) or p6s.get("status") == "OPERATOR_COMPLETE",
            str(p6s.get("status")),
        )
    except Exception as e:
        pkg("7-phase6-prereq", "Phase 6 operator prerequisite", False, str(e))

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    pkg("7-wheels", "Training wheels ON", wheels, f"wheels={wheels}")

    core_ids = {"7-pillars", "7-living", "7-roadmap", "7-wheels"}
    core = [p for p in packages if p["id"] in core_ids]
    complete = all(p["ok"] for p in core)

    locked = [
        {
            "id": "7B-product-soft-launch",
            "name": "Product soft launch",
            "status": "LOCKED",
            "reason": "metrics_go false until eligible LIVE honest rates",
        },
        {
            "id": "7C-autonomous-claim",
            "name": "Claim fully living autonomous agent",
            "status": "LOCKED",
            "reason": "checklist.autonomous_claim stays false by design",
        },
        {
            "id": "7D-wheels-off",
            "name": "Training wheels OFF",
            "status": "LOCKED",
            "reason": "measured lift on expanded suite required",
        },
    ]

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "7",
        "name": "North-star system package",
        "system_package_complete": complete,
        "status": "SYSTEM_PACKAGE_COMPLETE" if complete else "SYSTEM_PACKAGE_IN_PROGRESS",
        "packages": packages,
        "packages_ok": sum(1 for p in packages if p["ok"]),
        "packages_n": len(packages),
        "locked": locked,
        "training_wheels": wheels,
        "soft_launch_blocked": True,
        "autonomous_claim": False,
        "note": (
            "Phase 7 complete = pillars + living checklist + roadmap under wheels. "
            "This is the system package closeout — not product launch."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
