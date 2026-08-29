"""Honest product progress bar — what is built vs what is still locked.

Reads artifacts already on disk. Does not lift wheels. Does not claim
soft-launch. Writes artifacts/build_progress.json for dashboard + chat.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "build_progress.json"


def _load(rel: str) -> Dict[str, Any]:
    path = ROOT / rel
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _bar(done: float, total: float = 1.0, width: int = 20) -> str:
    if total <= 0:
        frac = 0.0
    else:
        frac = max(0.0, min(1.0, done / total))
    filled = int(round(frac * width))
    return "█" * filled + "░" * (width - filled)


def compute() -> Dict[str, Any]:
    gate = _load("artifacts/phase1_gate.json")
    p2 = _load("artifacts/phase2_status.json") or _load("artifacts/phase2a_status.json")
    p3s = _load("artifacts/phase3_status.json")
    p3go = _load("artifacts/phase3_go.json")
    sb242 = _load("artifacts/scoreboard_p1_242_live_merge_canary.json")
    sb247 = _load("artifacts/scoreboard_p1_247_ledger_canary.json")
    sb248 = _load("artifacts/scoreboard_p1_248_merge_replay.json")
    host = _load("artifacts/host_agent_status.json")
    last = _load("artifacts/host_agent_last_job.json")

    merge_ok = any(
        isinstance(r, dict) and r.get("fixture") == "merge" and r.get("ok") and r.get("mode") == "live"
        for r in (sb242.get("results") or []) + (sb248.get("results") or [])
    )
    ledger_ok = any(
        isinstance(r, dict) and r.get("fixture") == "ledger" and r.get("ok") and r.get("mode") == "live"
        for r in (sb247.get("results") or [])
    )
    hard_n = int(merge_ok) + int(ledger_ok)
    hard_total = 5  # merge ledger lru topo intervals

    metrics_go = bool(gate.get("metrics_go"))
    arch_go = bool(gate.get("architecture_go") or gate.get("status") in {"FULL_GO", "ARCH_GO"})
    wheels = bool(gate.get("training_wheels", True))
    if "training_wheels" not in gate:
        wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"

    items: List[Dict[str, Any]] = [
        {
            "id": "p1_metrics",
            "name": "Phase 1 eligible LIVE rate",
            "done": 1.0 if metrics_go else float(gate.get("honest_rate_eligible") or 0),
            "total": 1.0,
            "status": "DONE" if metrics_go else "OPEN",
            "detail": f"honest_rate_eligible={gate.get('honest_rate_eligible')} n={gate.get('live_eligible_n')}",
        },
        {
            "id": "p2_arch",
            "name": "Phase 2 architecture / strangler",
            "done": 1.0 if arch_go else 0.6,
            "total": 1.0,
            "status": "DONE" if arch_go else "ADVANCING",
            "detail": str(gate.get("status") or p2.get("status") or ""),
        },
        {
            "id": "hard_live",
            "name": "Hard LIVE skill (denied from eligible)",
            "done": float(hard_n),
            "total": float(hard_total),
            "status": "ADVANCING" if hard_n else "OPEN",
            "detail": f"merge={merge_ok} ledger={ledger_ok} remaining=lru,topo,intervals",
        },
        {
            "id": "p3_operator",
            "name": "Phase 3 evolution operator",
            "done": 1.0 if p3go.get("status") == "BUILD_OPEN" else 0.5,
            "total": 1.0,
            "status": str(p3go.get("status") or p3s.get("status") or "CODE_LANDED"),
            "detail": f"unlocked={p3go.get('unlocked')} measure_complete={p3s.get('measure_complete')}",
        },
        {
            "id": "desktop",
            "name": "One-click desktop host",
            "done": 0.7,
            "total": 1.0,
            "status": "ADVANCING",
            "detail": "ETHER.bat → start_ether_host.ps1; host must be running to drain jobs",
        },
        {
            "id": "soft_launch",
            "name": "Soft launch",
            "done": 0.0,
            "total": 1.0,
            "status": "LOCKED",
            "detail": "human ETHER_SOFT_LAUNCH=1 only; wheels stay ON",
        },
        {
            "id": "lora_train",
            "name": "LoRA weight updates",
            "done": 0.0,
            "total": 1.0,
            "status": "LOCKED",
            "detail": "dry-run only until dual flags + preference health",
        },
    ]

    weights = {
        "p1_metrics": 0.20,
        "p2_arch": 0.15,
        "hard_live": 0.20,
        "p3_operator": 0.15,
        "desktop": 0.10,
        "soft_launch": 0.10,
        "lora_train": 0.10,
    }
    overall = 0.0
    for it in items:
        frac = float(it["done"]) / float(it["total"] or 1.0)
        overall += weights.get(str(it["id"]), 0.0) * max(0.0, min(1.0, frac))
        it["bar"] = _bar(float(it["done"]), float(it["total"]))
        it["pct"] = round(100.0 * max(0.0, min(1.0, frac)))

    hb = str(host.get("heartbeat") or "")
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "overall_pct": round(100.0 * overall),
        "overall_bar": _bar(overall, 1.0),
        "training_wheels": wheels,
        "soft_launch": False,
        "metrics_go": metrics_go,
        "architecture_go": arch_go,
        "host_phase": host.get("phase"),
        "host_heartbeat": hb,
        "last_job_id": last.get("job_id"),
        "last_job_ok": last.get("ok"),
        "items": items,
        "work_left": [
            "Restart host if heartbeat stale — pending jobs do not drain otherwise",
            "Drain p1_245–249 + p3_10–12",
            "Prove ledger LIVE canary (still denied from eligible)",
            "Repeat merge once (p1_248)",
            "Keep Phase 3 operator ticking on idle",
            "Desktop shortcut must launch start_ether_host.ps1 (already does via ETHER.bat)",
            "Soft launch and LoRA train stay human-gated",
        ],
        "note": (
            "Overall is a weighted product bar, not the eligible-rate toy. "
            "Phase 1 rate gate can be 100% while the app is still mid-build."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
