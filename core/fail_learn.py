"""Classify artifacts/jobs/failed into typed lessons. Do not replay the graveyard."""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
FAILED = ROOT / "artifacts" / "jobs" / "failed"
OUT = ROOT / "artifacts" / "fail_learn.json"


def classify_name(name: str, note: str = "") -> str:
    hay = f"{name} {note}".lower()
    if "wheels_skip" in hay:
        return "wheels_skip"
    if "hard_tools_unit" in hay or "hard_live_tools" in hay or "hard_live_flex" in hay:
        return "unit_hard_tools"
    if "gate_sample" in hay and "merge" in hay:
        return "hard_live_observe_loop"
    if "gate_sample" in hay and any(x in hay for x in ("greeter", "wallet", "easy")):
        return "easy_gate_sample_stale"
    if "recompute" in hay or "eligible" in hay:
        return "rate_recompute_stale"
    if "archgo" in hay or "phase2a" in hay:
        return "arch_canary_stale"
    if "ledger" in hay:
        return "hard_live_ledger"
    if "timeout" in hay:
        return "timeout"
    return "other"


LEARN = {
    "wheels_skip": {
        "root_cause": "tool_order",
        "lesson": "job_class substring live over-matched pytest units. pytest argv is FAST.",
        "requeue": False,
        "fix": "core/job_class.py",
    },
    "unit_hard_tools": {
        "root_cause": "repair_quality",
        "lesson": "edit_lines after an insert shifts later line numbers. Use replace_once or anchor_edit.",
        "requeue": True,
        "fix": "core/hard_live_tools.py anchor_edit",
    },
    "hard_live_observe_loop": {
        "root_cause": "tool_order",
        "lesson": "4B looped read_file to max_steps. Numbered read + mutate tools + observe breaker. p1_242 PASS.",
        "requeue": False,
        "fix": "core/hard_live_tools.py + hard_live_boot.py",
    },
    "easy_gate_sample_stale": {
        "root_cause": "preference_pollution",
        "lesson": "Easy greeter/wallet samples do not grow the product. Do not replay. Eligible rate already 1.0.",
        "requeue": False,
        "fix": "none",
    },
    "rate_recompute_stale": {
        "root_cause": "infra",
        "lesson": "honest_rate_eligible already 1.0. Recompute FAILs are historical, not a current gate.",
        "requeue": False,
        "fix": "none",
    },
    "arch_canary_stale": {
        "root_cause": "infra",
        "lesson": "ARCH_GO already true. Do not replay p2a canary as if Phase 2 is open.",
        "requeue": False,
        "fix": "none",
    },
    "hard_live_ledger": {
        "root_cause": "repair_quality",
        "lesson": "Ledger is cross-file. Mutate transfer debit + total() via anchor_edit. Keep SEED_DENY.",
        "requeue": False,
        "fix": "p1_247 already queued as measure canary",
    },
    "timeout": {
        "root_cause": "budget_exhaust",
        "lesson": "Do not bump max_steps. Retire fixture from LIVE eligible. Diagnose tool_order first.",
        "requeue": False,
        "fix": "core/live_fixture_policy.py SEED_DENY",
    },
    "other": {
        "root_cause": "unknown",
        "lesson": "Do not blind-retry. Need a scoreboard or Labradorite critique.",
        "requeue": False,
        "fix": "none",
    },
}


def analyze() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    counts: Counter = Counter()
    if FAILED.exists():
        for path in sorted(FAILED.glob("*.json")):
            if path.name == ".gitkeep":
                continue
            note = ""
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    note = str(data.get("note") or "")
            except Exception:
                data = {}
            kind = classify_name(path.name, note)
            counts[kind] += 1
            rows.append({"file": path.name, "kind": kind, "id": (data or {}).get("id")})
    lessons = []
    for kind, n in counts.most_common():
        meta = LEARN[kind]
        lessons.append({"kind": kind, "n": n, **meta})
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "n_failed": len(rows),
        "counts": dict(counts),
        "lessons": lessons,
        "rows": rows,
        "policy": "Archive or ignore stale kinds. Requeue only unit_hard_tools after the tool fix.",
        "soft_launch": False,
        "training_wheels": True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2))
