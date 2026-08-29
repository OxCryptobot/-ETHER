"""Phase 3 evolution operator — build evolved ETHER after metrics_go.

Unlocked when phase1 metrics_go is true AND at least one hard LIVE canary
scored PASS. Does not lift training wheels. Does not set ETHER_SOFT_LAUNCH.
Does not write hard LIVE rows into the eligible denominator.

What this module actually does:
- persist AgentState for the phase-3 thread
- run a dry evolution cycle (Selenite plan + optional Labradorite)
- turn the latest critique into a draft pending-job envelope
- publish artifacts/phase3_go.json so the host/dashboard can see BUILD_OPEN
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
ARTIFACTS = ROOT / "artifacts"
PENDING = ARTIFACTS / "jobs" / "pending"
GO_PATH = ARTIFACTS / "phase3_go.json"
TICK_PATH = ARTIFACTS / "phase3_evolve_tick.json"

HARD_CANARY_SCOREBOARDS = (
    "scoreboard_p1_242_live_merge_canary.json",
    "scoreboard_p1_248_merge_replay.json",
    "scoreboard_p1_247_ledger_canary.json",
)

SEED_DENY = {
    "ledger",
    "pipeline_ledger",
    "ss_pipeline_ledger",
    "lru",
    "topo",
    "intervals",
    "merge",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _metrics_go() -> Dict[str, Any]:
    gate = _read_json(ARTIFACTS / "phase1_gate.json")
    return {
        "metrics_go": bool(gate.get("metrics_go")),
        "architecture_go": bool(gate.get("architecture_go")),
        "honest_rate_eligible": gate.get("honest_rate_eligible"),
        "live_eligible_n": gate.get("live_eligible_n"),
        "status": gate.get("status"),
        "training_wheels": gate.get("training_wheels", True),
    }


def _hard_canary_pass() -> Dict[str, Any]:
    hits: List[Dict[str, Any]] = []
    for name in HARD_CANARY_SCOREBOARDS:
        path = ARTIFACTS / name
        data = _read_json(path)
        for row in data.get("results") or []:
            if not isinstance(row, dict):
                continue
            fx = str(row.get("fixture") or "").lower()
            mode = str(row.get("mode") or "").lower()
            if mode != "live":
                continue
            if fx not in SEED_DENY and fx not in {"merge", "ledger", "lru", "topo", "intervals"}:
                continue
            hits.append(
                {
                    "file": name,
                    "fixture": fx,
                    "ok": bool(row.get("ok")),
                    "score": row.get("score"),
                    "n_steps": row.get("n_steps"),
                    "reason": row.get("reason"),
                    "tools": row.get("tools") or [],
                }
            )
    passed = [h for h in hits if h.get("ok") and float(h.get("score") or 0) >= 0.99]
    return {"hits": hits, "passed": passed, "n_pass": len(passed), "ok": bool(passed)}


def phase3_unlocked() -> bool:
    g = _metrics_go()
    c = _hard_canary_pass()
    return bool(g.get("metrics_go")) and bool(c.get("ok"))


def _persist_state(*, objective: str, hypothesis: str, meta: Dict[str, Any]) -> str:
    from core.agent_state import AgentState

    state = AgentState.load_or_create("phase3_evolve")
    state.objective = objective[:500]
    state.hypothesis = hypothesis[:300]
    state.training_wheels = True
    state.meta.update(meta)
    state.meta["phase"] = "3"
    state.meta["soft_launch"] = False
    state.save()
    return state.thread_id


def draft_job_from_critique(critique: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    """One-hypothesis measure/fast envelope. Never marks hard LIVE eligible."""
    smallest = critique.get("smallest_experiment") or {}
    if not isinstance(smallest, dict):
        smallest = {}
    change = str(smallest.get("change") or critique.get("root_cause") or "evolve tick")
    fx = "ledger"
    text = json.dumps(critique, default=str).lower()
    for name in ("merge", "ledger", "lru", "topo", "intervals"):
        if name in text:
            fx = name
            break
    return {
        "id": job_id,
        "class": "measure",
        "continue_on_fail": True,
        "note": (
            f"Phase3 draft from critique root_cause={critique.get('root_cause')}. "
            f"Denied from eligible. {change[:160]}"
        ),
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "scripts.batch_phase_d",
                    "--arm",
                    "direct",
                    "--mode",
                    "scripted",
                    "--fixture",
                    fx,
                    "--max-steps",
                    "8",
                    "--timeout",
                    "120",
                    "--scoreboard",
                    f"artifacts/scoreboard_{job_id}.json",
                ],
                "timeout": 180,
            }
        ],
    }


def maybe_write_pending(job: Dict[str, Any], *, write: bool) -> Optional[str]:
    if not write:
        return None
    PENDING.mkdir(parents=True, exist_ok=True)
    jid = str(job.get("id") or "p3_evolve_draft")
    path = PENDING / f"{jid}.json"
    if path.exists():
        return str(path.relative_to(ROOT)).replace("\\", "/")
    existing = {p.name for p in PENDING.glob("*.json")}
    if len(existing) >= 8:
        return None
    _write_json(path, job)
    return str(path.relative_to(ROOT)).replace("\\", "/")


def tick(*, enqueue: bool = False, force_critique: bool = False) -> Dict[str, Any]:
    """One Phase 3 evolution tick. Safe to run on the host every idle cycle."""
    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    gate = _metrics_go()
    canary = _hard_canary_pass()
    unlocked = bool(gate.get("metrics_go")) and bool(canary.get("ok"))

    objective = (
        "Phase 3 evolved ETHER: durable AgentState, critique-to-plan, "
        "dry LoRA, hard-LIVE skill without eligible poison."
    )
    hypothesis = (
        "After metrics_go + one hard LIVE PASS, build the evolution operator "
        "instead of farming easy fixtures."
    )
    thread_id = _persist_state(
        objective=objective,
        hypothesis=hypothesis,
        meta={
            "metrics_go": gate.get("metrics_go"),
            "hard_canary_n_pass": canary.get("n_pass"),
            "unlocked": unlocked,
        },
    )

    evo: Dict[str, Any] = {}
    try:
        from core.evolution_loop import run_evolution_cycle

        fail_ctx = None
        if force_critique or not canary.get("ok"):
            fail_ctx = {
                "reason": "tool_order" if not canary.get("ok") else "measure",
                "n_steps": 0,
                "mutation": "phase3_evolve",
            }
        evo = run_evolution_cycle(
            objective=objective,
            original_failure=fail_ctx,
            thread_id=thread_id,
            mode="unit",
        )
    except Exception as exc:
        evo = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    wire: Dict[str, Any] = {}
    try:
        from core.critique_plan_wire import wire_latest

        wire = wire_latest(limit=8)
    except Exception as exc:
        wire = {"ok": False, "error": str(exc)[:160]}

    dry: Dict[str, Any] = {}
    try:
        from core.lora_dry_tick import dry_tick

        dry = dry_tick(force=True)
    except Exception as exc:
        dry = {"ok": False, "trained": False, "dry_run": True, "error": str(exc)[:160]}

    draft = None
    draft_path = None
    crit = {
        "root_cause": evo.get("root_cause") or "phase3_build",
        "smallest_experiment": evo.get("smallest_experiment")
        or {"change": "scripted hard ledger then live canary denied from eligible"},
    }
    if unlocked:
        draft = draft_job_from_critique(crit, job_id="p3_13_scripted_hard_ledger")
        draft_path = maybe_write_pending(draft, write=enqueue)

    go = {
        "updated": _now(),
        "phase": "3",
        "status": "BUILD_OPEN" if unlocked and wheels else "BLOCKED",
        "unlocked": unlocked,
        "metrics_go": gate.get("metrics_go"),
        "architecture_go": gate.get("architecture_go"),
        "hard_live_canary_pass": canary.get("n_pass"),
        "hard_live_canaries": canary.get("passed"),
        "training_wheels": wheels,
        "soft_launch": False,
        "lora_train": False,
        "eligible_denylist": sorted(SEED_DENY),
        "note": (
            "Phase 3 BUILD_OPEN = metrics_go + ≥1 hard LIVE canary PASS. "
            "Wheels stay ON. Soft launch remains a human flag. "
            "Hard fixtures stay off the eligible denominator."
        ),
    }
    _write_json(GO_PATH, go)

    tick_payload: Dict[str, Any] = {
        "updated": _now(),
        "ok": bool(unlocked and wheels and evo.get("ok", True)),
        "unlocked": unlocked,
        "thread_id": thread_id,
        "gate": gate,
        "canary": {"n_pass": canary.get("n_pass"), "passed": canary.get("passed")},
        "evolution_ok": evo.get("ok"),
        "evolution_path": evo.get("evolution_path"),
        "root_cause": evo.get("root_cause"),
        "wire": {
            "n_critiques": wire.get("n_critiques"),
            "n_replanned": wire.get("n_replanned"),
        },
        "lora_dry": {
            "ok": dry.get("ok"),
            "trained": dry.get("trained"),
            "dry_run": dry.get("dry_run"),
        },
        "draft_job_id": (draft or {}).get("id"),
        "draft_written": draft_path,
        "soft_launch": False,
        "path": str(TICK_PATH.relative_to(ROOT)).replace("\\", "/"),
    }
    _write_json(TICK_PATH, tick_payload)
    return tick_payload


def publish_go() -> Dict[str, Any]:
    return tick(enqueue=False, force_critique=False)


if __name__ == "__main__":
    print(json.dumps(tick(enqueue=False), indent=2, default=str))
