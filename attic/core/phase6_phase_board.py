"""Phase 6 — unified phase board rollup (1–5).

Read status artifacts; does not change gates.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase6_phase_board.json"
ART = ROOT / "artifacts"


def _load(name: str) -> Dict[str, Any]:
    p = ART / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _row(phase: str, name: str, status: str, detail: str = "") -> Dict[str, Any]:
    return {"phase": phase, "name": name, "status": status, "detail": detail[:120]}


def board() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []

    p1 = _load("phase1_gate.json")
    rows.append(
        _row(
            "1",
            "Gate metrics / ARCH",
            str(p1.get("status") or "UNKNOWN"),
            f"metrics_go={p1.get('metrics_go')} arch={p1.get('architecture_go')}",
        )
    )

    p2 = _load("phase2_status.json")
    rows.append(
        _row(
            "2",
            "Architecture",
            str(p2.get("status") or "UNKNOWN"),
            f"complete={p2.get('architecture_complete')}",
        )
    )

    p3 = _load("phase3_status.json")
    rows.append(
        _row(
            "3",
            "Evolution measure",
            str(p3.get("status") or "UNKNOWN"),
            f"complete={p3.get('measure_complete')}",
        )
    )

    p4 = _load("phase4_status.json")
    rows.append(
        _row(
            "4",
            "Capability scaffolds",
            str(p4.get("status") or "UNKNOWN"),
            f"complete={p4.get('scaffold_complete')}",
        )
    )

    p5 = _load("phase5_status.json")
    rows.append(
        _row(
            "5",
            "Experiment registry",
            str(p5.get("status") or "UNKNOWN"),
            f"complete={p5.get('experiment_complete')}",
        )
    )

    # Live compute fallbacks when artifacts missing
    try:
        if not p2:
            from core.phase2_status import compute as c2

            x = c2()
            rows[1] = _row("2", "Architecture", str(x.get("status")), f"complete={x.get('architecture_complete')}")
        if not p3:
            from core.phase3_status import compute as c3

            x = c3()
            rows[2] = _row("3", "Evolution measure", str(x.get("status")), f"complete={x.get('measure_complete')}")
        if not p4:
            from core.phase4_status import compute as c4

            x = c4()
            rows[3] = _row("4", "Capability scaffolds", str(x.get("status")), f"complete={x.get('scaffold_complete')}")
        if not p5:
            from core.phase5_status import compute as c5

            x = c5()
            rows[4] = _row("5", "Experiment registry", str(x.get("status")), f"complete={x.get('experiment_complete')}")
    except Exception:
        pass

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "6",
        "board": rows,
        "n": len(rows),
        "training_wheels": wheels,
        "soft_launch_blocked": True,
        "ok": len(rows) == 5,
        "note": "Unified board. Soft launch still blocked regardless of ARCH/MEASURE/SCAFFOLD green.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(board(), indent=2))
