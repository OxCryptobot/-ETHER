"""Phase 5 status — experimental / moonshot research package.

EXPERIMENT_COMPLETE when moonshot registry, lessons inventory, and
research flags (all OFF) pass under wheels ON.

Live experiment flags remain LOCKED.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase5_status.json"


def compute() -> Dict[str, Any]:
    packages: List[Dict[str, Any]] = []

    def pkg(pid: str, name: str, ok: bool, detail: str = "") -> None:
        packages.append(
            {"id": pid, "name": name, "ok": bool(ok), "detail": detail[:160]}
        )

    try:
        from core.phase5_moonshots import registry

        m = registry()
        pkg(
            "5-moonshots",
            "Moonshot research registry",
            bool(m.get("ok")),
            f"n={m.get('n')} artifacts={m.get('artifact_present_n')}",
        )
    except Exception as e:
        pkg("5-moonshots", "Moonshot research registry", False, str(e))

    try:
        from core.phase5_lessons import inventory

        les = inventory()
        pkg(
            "5-lessons",
            "Lessons journal inventory",
            bool(les.get("ok")),
            f"n={les.get('n_lessons')}",
        )
    except Exception as e:
        pkg("5-lessons", "Lessons journal inventory", False, str(e))

    try:
        from core.phase5_research_flags import board

        b = board()
        pkg(
            "5-flags",
            "Research flags all OFF",
            bool(b.get("ok")),
            f"any_on={b.get('any_experimental_on')} wheels={b.get('training_wheels')}",
        )
    except Exception as e:
        pkg("5-flags", "Research flags all OFF", False, str(e))

    try:
        from core.phase4_status import compute as p4

        p4s = p4()
        pkg(
            "5-phase4-prereq",
            "Phase 4 scaffold prerequisite",
            bool(p4s.get("scaffold_complete")) or p4s.get("status") == "SCAFFOLD_COMPLETE",
            str(p4s.get("status")),
        )
    except Exception as e:
        pkg("5-phase4-prereq", "Phase 4 scaffold prerequisite", False, str(e))

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    pkg("5-wheels", "Training wheels ON", wheels, f"wheels={wheels}")

    core_ids = {"5-moonshots", "5-lessons", "5-flags", "5-wheels"}
    core = [p for p in packages if p["id"] in core_ids]
    complete = all(p["ok"] for p in core)

    locked = [
        {
            "id": "5B-shadow-live",
            "name": "ETHER_SHADOW_LIVE parallel oracle",
            "status": "LOCKED",
            "reason": "GPU cost; post metrics_go only",
        },
        {
            "id": "5C-auto-experiment",
            "name": "Auto-enable experimental flags",
            "status": "LOCKED",
            "reason": "human-only; research board must stay green",
        },
        {
            "id": "5D-cross-repo-write",
            "name": "Cross-repository write agents",
            "status": "LOCKED",
            "reason": "read-only research until isolation model",
        },
        {
            "id": "5E-unbounded-self-mod",
            "name": "Unbounded self-modification",
            "status": "LOCKED",
            "reason": "Controlled Evolution pillar — template + gate only",
        },
    ]

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "5",
        "name": "Experimental / moonshot research",
        "experiment_complete": complete,
        "status": "EXPERIMENT_COMPLETE" if complete else "EXPERIMENT_IN_PROGRESS",
        "packages": packages,
        "packages_ok": sum(1 for p in packages if p["ok"]),
        "packages_n": len(packages),
        "locked": locked,
        "training_wheels": wheels,
        "soft_launch_blocked": True,
        "note": (
            "Phase 5 complete = moonshot registry + lessons inventory + flags OFF. "
            "No live experiments auto-enabled."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
