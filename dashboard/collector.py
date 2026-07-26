"""Collect live system state for the Control Matrix (intelligence + ledger)."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]

GEMS = [
    {"id": "clear-quartz", "role": "Sandbox + harness", "layer": "verify"},
    {"id": "rose-quartz", "role": "LLM router", "layer": "generate"},
    {"id": "citrine", "role": "Workspace memory", "layer": "memory"},
    {"id": "selenite", "role": "Planner", "layer": "plan"},
    {"id": "amethyst", "role": "Learning log", "layer": "learn"},
    {"id": "black-tourmaline", "role": "Security audit", "layer": "verify"},
    {"id": "labradorite", "role": "Critique", "layer": "review"},
    {"id": "grandidierite", "role": "Tool extension", "layer": "extend"},
]


def _read_json(path: Path) -> Optional[Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except Exception:
        return ""


def _tail_jsonl(path: Path, limit: int = 40) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return list(reversed(rows))


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:
        return 0


def _parse_tasks(md: str) -> Dict[str, Any]:
    batches: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    row_re = re.compile(
        r"^\|\s*(\d+)\s*\|\s*([^|]*?)\s*\|\s*([^|]+?)\s*\|(?:\s*([^|]*?)\s*\|)?\s*$"
    )
    section = "unknown"
    for line in md.splitlines():
        sm = re.match(r"^##\s+(.+)$", line.strip())
        if sm:
            section = sm.group(1).strip()
            if any(k in section.lower() for k in ("batch", "done", "active", "p0", "next")):
                current = {"name": section, "tasks": []}
                batches.append(current)
            continue
        m = row_re.match(line.strip())
        if not m or current is None:
            continue
        num, col2, col3, col4 = m.group(1), m.group(2).strip(), m.group(3).strip(), (m.group(4) or "").strip()
        if not num.isdigit():
            continue
        status = "done" if "done" in section.lower() else "queued"
        current["tasks"].append(
            {
                "id": int(num),
                "title": col2[:120] if status == "done" else col3[:120],
                "status": status,
                "priority": col2[:8] if status != "done" else "",
                "notes": (col3 if status == "done" else col4)[:100],
            }
        )
    all_tasks = [t for b in batches for t in b["tasks"]]
    done = sum(1 for t in all_tasks if t["status"] == "done")
    return {
        "batches": batches,
        "totals": {"done": done, "queued": len(all_tasks) - done, "total": len(all_tasks)},
        "progress_pct": round(100 * done / len(all_tasks), 1) if all_tasks else 0.0,
    }


def _intel_block() -> Dict[str, Any]:
    try:
        from core.health_metric import compute_health

        health = compute_health()
    except Exception:
        health = _read_json(ROOT / "memory" / "bench" / "health.json") or {}
    try:
        from core.bench_guardian import evaluate

        guardian = evaluate()
    except Exception:
        guardian = _read_json(ROOT / "memory" / "bench" / "guardian.json") or {}
    try:
        from core.ledger import compute_ledger

        ledger = compute_ledger()
    except Exception:
        ledger = _read_json(ROOT / "memory" / "ledger" / "latest.json") or {}

    curriculum = _read_json(ROOT / "memory" / "curriculum" / "state.json") or {}
    pass_n = _count_jsonl(ROOT / "memory" / "experience" / "pass.jsonl")
    fail_n = _count_jsonl(ROOT / "memory" / "experience" / "fail.jsonl")
    recent_pass = _tail_jsonl(ROOT / "memory" / "experience" / "pass.jsonl", 8)
    recent_fail = _tail_jsonl(ROOT / "memory" / "experience" / "fail.jsonl", 5)
    failure_graph = _read_json(ROOT / "memory" / "experience" / "failure_graph.json") or {}
    nodes = failure_graph.get("nodes") or {}
    top_fails = sorted(
        ({"sig": k, "count": v.get("count", 0), "kind": v.get("kind")} for k, v in nodes.items()),
        key=lambda x: x["count"],
        reverse=True,
    )[:6]
    bench_latest = _read_json(ROOT / "memory" / "bench" / "latest.json") or {}
    quiz = _read_json(ROOT / "memory" / "quiz" / "latest.json") or {}

    return {
        "primary_metric": health.get("primary_metric") or "bench_pass_rate",
        "pass_rate": health.get("pass_rate"),
        "pass_rate_avg7": health.get("pass_rate_avg7"),
        "latency_s_avg7": health.get("latency_s_avg7"),
        "healthy": health.get("healthy"),
        "stale": health.get("stale"),
        "guardian_frozen": guardian.get("frozen") or health.get("guardian_frozen"),
        "guardian_reason": guardian.get("reason") or health.get("guardian_reason"),
        "curriculum_tier": curriculum.get("tier", 0),
        "curriculum_wins": curriculum.get("wins", 0),
        "curriculum_losses": curriculum.get("losses", 0),
        "curriculum_event": curriculum.get("last_event"),
        "experience_pass": pass_n,
        "experience_fail": fail_n,
        "recent_pass": [
            {"title": (r.get("objective") or "")[:60], "conf": r.get("confidence"), "strategy": r.get("strategy")}
            for r in recent_pass
        ],
        "recent_fail": [
            {"title": (r.get("objective") or "")[:60], "kind": r.get("fail_kind")}
            for r in recent_fail
        ],
        "top_failure_signatures": top_fails,
        "bench_n": bench_latest.get("n"),
        "bench_pass": bench_latest.get("pass"),
        "bench_ts": bench_latest.get("timestamp"),
        "quiz_pass_rate": quiz.get("pass_rate"),
        "ledger": {
            "avg_run_ms": ledger.get("avg_run_ms"),
            "p50_run_ms": ledger.get("p50_run_ms"),
            "local_runs": ledger.get("local_runs"),
            "burst_flagged_runs": ledger.get("burst_flagged_runs"),
            "burst_ledger_calls": ledger.get("burst_ledger_calls"),
            "burst_tokens_sum": ledger.get("burst_tokens_sum"),
            "stage_avg_ms": ledger.get("stage_avg_ms") or {},
            "cost_note": ledger.get("cost_note"),
        },
    }


def _current_work(runs: List[Dict[str, Any]], heartbeat: Optional[str], latest: Dict[str, Any]) -> Dict[str, Any]:
    from core.progress import read_progress

    live = read_progress()
    latest_run = runs[0] if runs else None
    activity = []
    if live:
        activity.append({"stage": live.get("stage"), "ok": True, "detail": live.get("detail"), "ms": None})
    if latest_run:
        for s in latest_run.get("stages") or []:
            activity.append(
                {
                    "stage": s.get("stage"),
                    "ok": s.get("success"),
                    "detail": s.get("detail"),
                    "ms": s.get("duration_ms"),
                }
            )
    gates = (latest or {}).get("gates") or {}
    steps = (latest or {}).get("steps") or {}
    phase = "idle"
    if live:
        phase = f"live:{live.get('stage')}"
    elif heartbeat:
        phase = "autonomy_cycle"
    if latest_run and not live:
        st = latest_run.get("status")
        phase = "last_run_complete" if st == "complete" else ("last_run_error" if st == "error" else phase)

    return {
        "phase": phase,
        "heartbeat": heartbeat,
        "objective": (live or {}).get("objective") or (latest_run or {}).get("objective"),
        "status": (latest_run or {}).get("status"),
        "confidence": (latest_run or {}).get("confidence"),
        "strategy": (latest_run or {}).get("strategy"),
        "reward": (latest_run or {}).get("reward"),
        "started_at": (live or {}).get("updated_at") or (latest_run or {}).get("started_at"),
        "stages": activity[:20],
        "flywheel_ok": (latest or {}).get("ok"),
        "flywheel_conf": gates.get("confidence"),
        "matrix": [
            {
                "name": k,
                "ok": v.get("ok"),
                "ms": int((v.get("duration_s") or 0) * 1000),
                "error": (v.get("error_brief") or v.get("healed") or "")[:120],
            }
            for k, v in steps.items()
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def collect_snapshot() -> Dict[str, Any]:
    flywheel_dir = ROOT / "memory" / "flywheel"
    runs_dir = ROOT / "memory" / "runs"
    tools_q = ROOT / "tools" / "quarantine"
    tools_p = ROOT / "tools" / "persistent"

    latest = _read_json(flywheel_dir / "latest.json") or {}
    last_fail = _read_json(flywheel_dir / "last_fail.json")
    history = _tail_jsonl(flywheel_dir / "history.jsonl", 50)
    heartbeat = _read_text(flywheel_dir / "heartbeat.txt").strip()
    fabricate_log = _tail_jsonl(ROOT / "memory" / "tools" / "fabricate.jsonl", 20)
    bandit = _read_json(ROOT / "memory" / "learning" / "bandit.json") or {}
    fail_streak = _read_json(ROOT / "memory" / "learning" / "fail_streak.json") or {}
    tasks_md = _read_text(ROOT / "TASKS.md")
    tasks = _parse_tasks(tasks_md)
    intel = _intel_block()

    runs: List[Dict[str, Any]] = []
    if runs_dir.exists():
        files = sorted(
            [p for p in runs_dir.glob("*.json") if p.name != "in_progress.json"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:25]
        for f in files:
            data = _read_json(f)
            if not isinstance(data, dict):
                continue
            runs.append(
                {
                    "id": data.get("task_id") or f.stem,
                    "objective": (data.get("objective") or "")[:140],
                    "status": data.get("status"),
                    "confidence": data.get("confidence"),
                    "started_at": data.get("started_at"),
                    "retries": data.get("retries", 0),
                    "strategy": data.get("strategy"),
                    "reward": data.get("reward"),
                    "stages": [
                        {
                            "stage": s.get("stage"),
                            "success": s.get("success"),
                            "detail": (s.get("detail") or "")[:60],
                            "duration_ms": round(float(s.get("duration_ms") or 0), 1),
                        }
                        for s in (data.get("stages") or [])
                    ],
                }
            )

    confs = [float(r["confidence"]) for r in runs if r.get("confidence") is not None]
    avg_conf = round(sum(confs) / len(confs), 3) if confs else None
    complete = sum(1 for r in runs if r.get("status") == "complete")
    errors = sum(1 for r in runs if r.get("status") == "error")
    fw_pass = sum(1 for h in history if h.get("ok"))
    fw_total = len(history) or 1

    quarantine = sorted(p.name for p in tools_q.glob("*.py")) if tools_q.exists() else []
    persistent = sorted(p.name for p in tools_p.glob("*.py")) if tools_p.exists() else []

    arms = bandit.get("arms") or {}
    bandit_ranked = sorted(
        (
            {
                "strategy": k,
                "pulls": v.get("pulls", 0),
                "mean": round((v.get("total_reward", 0) / v["pulls"]) if v.get("pulls") else 0, 4),
            }
            for k, v in arms.items()
        ),
        key=lambda x: x["mean"],
        reverse=True,
    )

    current_work = _current_work(runs, heartbeat or None, latest)
    gates = (latest or {}).get("gates") or {}
    steps = (latest or {}).get("steps") or {}
    ledger = (intel.get("ledger") or {})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": "@ETHER",
        "version": "0.2.1",
        "heartbeat": heartbeat or None,
        "current_work": current_work,
        "intelligence": intel,
        "ledger": ledger,
        "tasks": tasks,
        "summary": {
            "quality_pass": (latest or {}).get("ok"),
            "confidence": gates.get("confidence"),
            "audit": gates.get("audit_approved"),
            "reason": gates.get("agentic_reason"),
            "model": os.getenv("ETHER_PRIMARY_MODEL", ""),
            "flywheel_pass_rate": round(fw_pass / fw_total, 3) if history else None,
            "cycles": len(history),
            "runs_complete": complete,
            "runs_error": errors,
            "avg_run_confidence": avg_conf,
            "fail_streak": fail_streak.get("streak", 0),
            "bench_pass_rate": intel.get("pass_rate"),
            "quiz_pass_rate": intel.get("quiz_pass_rate"),
            "healthy": intel.get("healthy"),
            "curriculum_tier": intel.get("curriculum_tier"),
            "experience_pass": intel.get("experience_pass"),
            "avg_run_ms": ledger.get("avg_run_ms"),
            "burst_calls": ledger.get("burst_ledger_calls"),
            "pull_error": (steps.get("pull") or {}).get("error_brief")
            or (steps.get("pull") or {}).get("healed"),
        },
        "workflow": [
            {"id": 1, "name": "Pull", "desc": "git self-heal"},
            {"id": 2, "name": "Static", "desc": "smoke + pytest"},
            {"id": 3, "name": "Curriculum", "desc": "graded objective"},
            {"id": 4, "name": "Retrieve", "desc": "experience + BM25"},
            {"id": 5, "name": "Code", "desc": "Rose Quartz + strategy"},
            {"id": 6, "name": "Synth/prep", "desc": "test_synth + scratch patch"},
            {"id": 7, "name": "Sandbox", "desc": "Clear Quartz"},
            {"id": 8, "name": "Audit + learn", "desc": "vault + bandit + report"},
        ],
        "matrix_steps": [
            {
                "name": k,
                "ok": v.get("ok"),
                "ms": int((v.get("duration_s") or 0) * 1000),
                "error": (v.get("error_brief") or ("healed:" + str(v["healed"]) if v.get("healed") else ""))[:160],
            }
            for k, v in steps.items()
        ],
        "history": [
            {
                "ts": h.get("timestamp"),
                "ok": h.get("ok"),
                "conf": (h.get("gates") or {}).get("confidence"),
                "reason": (h.get("gates") or {}).get("agentic_reason"),
            }
            for h in history[:24]
        ],
        "runs": runs,
        "gems": GEMS,
        "tools": {
            "quarantine": quarantine,
            "persistent": persistent,
            "persistent_count": len(persistent),
            "quarantine_count": len(quarantine),
        },
        "fabricate_log": [
            {
                "name": e.get("name"),
                "status": e.get("validation_status"),
                "path": e.get("quarantine_path"),
                "promoted": e.get("promoted"),
                "ts": e.get("timestamp"),
            }
            for e in fabricate_log
        ],
        "learning": {
            "epsilon": bandit.get("epsilon"),
            "ranked": bandit_ranked[:10],
            "fail_streak": fail_streak,
        },
        "skills": [
            {"name": "curriculum", "status": f"tier {intel.get('curriculum_tier', 0)}"},
            {"name": "experience vault", "status": f"{intel.get('experience_pass', 0)} pass / {intel.get('experience_fail', 0)} fail"},
            {"name": "bench guardian", "status": "FROZEN" if intel.get("guardian_frozen") else "ok"},
            {"name": "ledger", "status": f"avg {ledger.get('avg_run_ms')}ms"},
            {"name": "burst", "status": f"calls {ledger.get('burst_ledger_calls', 0)}"},
            {"name": "flywheel", "status": "active" if heartbeat else "idle"},
        ],
        "benchmarks": {
            "primary": "bench_pass_rate",
            "pass_rate": intel.get("pass_rate"),
            "quiz_pass_rate": intel.get("quiz_pass_rate"),
            "pass_rate_avg7": intel.get("pass_rate_avg7"),
            "healthy": intel.get("healthy"),
            "flywheel_cycles": len(history),
            "flywheel_pass_rate": round(fw_pass / fw_total, 3) if history else None,
            "pipeline_success_rate": round(complete / max(1, complete + errors), 3),
            "avg_confidence": avg_conf,
            "avg_run_ms": ledger.get("avg_run_ms"),
            "last_fail_reason": ((last_fail or {}).get("gates") or {}).get("agentic_reason"),
        },
        "connections": {
            "docker": shutil.which("docker") is not None,
            "ollama": shutil.which("ollama") is not None,
            "qdrant_url": os.getenv("QDRANT_URL", "http://localhost:6333"),
            "ollama_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            "primary_model": os.getenv("ETHER_PRIMARY_MODEL", ""),
            "burst": os.getenv("ETHER_BURST", "0") == "1",
        },
        "policy": {
            "min_confidence": float(os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7")),
            "max_retries": int(os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3")),
            "interval_s": int(os.getenv("ETHER_FLYWHEEL_INTERVAL", "900")),
            "push": os.getenv("ETHER_FLYWHEEL_PUSH", "0") == "1",
            "curriculum": os.getenv("ETHER_CURRICULUM", "1") == "1",
            "experience": os.getenv("ETHER_EXPERIENCE", "1") == "1",
            "guardian": os.getenv("ETHER_BENCH_GUARDIAN", "1") == "1",
            "burst_on_fail": os.getenv("ETHER_BURST_ON_FAIL", "1") == "1",
        },
        "docs": {
            "status": _read_text(ROOT / "STATUS.md")[:1800],
            "onboarding": _read_text(ROOT / "ONBOARDING.md")[:1200],
            "methodology": _read_text(ROOT / "METHODOLOGY.md")[:1200],
        },
        "latest": latest,
        "last_fail": last_fail,
    }
