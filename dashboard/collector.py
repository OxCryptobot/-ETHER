"""Collect live system state for Control Matrix — never throws to caller."""

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
    {"id": "clear-quartz", "role": "Sandbox + test harness", "layer": "verify",
     "tip": "Runs generated code in Docker or local subprocess. Scores exit + asserts."},
    {"id": "rose-quartz", "role": "LLM router (local + burst)", "layer": "generate",
     "tip": "Calls Ollama primary model; optional cloud burst on retry / hard tasks."},
    {"id": "citrine", "role": "Workspace memory / RAG", "layer": "memory",
     "tip": "Vector or offline BM25 context from your repo."},
    {"id": "selenite", "role": "Planner", "layer": "plan",
     "tip": "Turns objectives into steps; may request tools."},
    {"id": "amethyst", "role": "Learning log", "layer": "learn",
     "tip": "Stores interaction logs for bandit + analysis."},
    {"id": "black-tourmaline", "role": "Security audit", "layer": "verify",
     "tip": "Static risk scan before code is trusted."},
    {"id": "labradorite", "role": "Critique", "layer": "review",
     "tip": "Optional complexity / quality critique."},
    {"id": "grandidierite", "role": "Tool fabricate / registry", "layer": "extend",
     "tip": "Creates quarantine tools; promote only after reconcile."},
]

WORKFLOW = [
    {"id": 1, "name": "Pull", "desc": "git fetch/self-heal", "tip": "Updates code; soft-fail if dirty unless ETHER_GIT_RESET_OK=1"},
    {"id": 2, "name": "Static", "desc": "smoke + pytest", "tip": "If tests fail, agentic stage is skipped"},
    {"id": 3, "name": "Doctor", "desc": "deps check", "tip": "Ollama + sandbox backend + manifest"},
    {"id": 4, "name": "Curriculum", "desc": "graded objective", "tip": "Picks harder tasks as verified wins grow"},
    {"id": 5, "name": "Retrieve", "desc": "experience + BM25", "tip": "Few-shot from vault + repo context"},
    {"id": 6, "name": "Code", "desc": "Rose Quartz", "tip": "Local model; burst only on policy"},
    {"id": 7, "name": "Sandbox", "desc": "Clear Quartz", "tip": "Must pass asserts for verification_score"},
    {"id": 8, "name": "Audit + learn", "desc": "vault + bandit + report", "tip": "Gate on confidence then push report"},
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
            if not line.strip():
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


def _sandbox_info() -> Dict[str, Any]:
    raw = (os.getenv("ETHER_SANDBOX_BACKEND") or "auto").strip().lower()
    docker = shutil.which("docker") is not None
    py = os.getenv("ETHER_SANDBOX_PYTHON") or ("python3" if os.name != "nt" else "python")
    if raw in ("local", "subprocess", "native"):
        effective = "local"
    elif raw == "docker":
        effective = "docker" if docker else "local (fallback)"
    else:
        effective = "docker" if docker else "local"
    return {"configured": raw, "effective": effective, "docker_present": docker, "python": py}


def _intel_block() -> Dict[str, Any]:
    health: Dict[str, Any] = {}
    try:
        from core.health_metric import compute_health

        health = compute_health() or {}
    except Exception:
        health = _read_json(ROOT / "memory" / "bench" / "health.json") or {}
    guardian: Dict[str, Any] = {}
    try:
        from core.bench_guardian import evaluate

        guardian = evaluate() or {}
    except Exception:
        guardian = _read_json(ROOT / "memory" / "bench" / "guardian.json") or {}
    ledger: Dict[str, Any] = {}
    try:
        from core.ledger import compute_ledger

        ledger = compute_ledger() or {}
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
    dataset = _read_json(ROOT / "memory" / "quiz" / "dataset_latest.json") or {}
    ablation = _read_json(ROOT / "memory" / "bench" / "ablation_latest.json") or {}

    unhealthy = health.get("unhealthy_reasons") or health.get("reasons") or []
    if isinstance(unhealthy, str):
        unhealthy = [unhealthy]

    return {
        "primary_metric": health.get("primary_metric") or "bench_pass_rate",
        "pass_rate": health.get("pass_rate"),
        "pass_rate_avg7": health.get("pass_rate_avg7"),
        "latency_s_avg7": health.get("latency_s_avg7"),
        "healthy": health.get("healthy"),
        "stale": health.get("stale"),
        "unhealthy_reasons": list(unhealthy),
        "guardian_frozen": guardian.get("frozen") or health.get("guardian_frozen"),
        "guardian_reason": guardian.get("reason") or health.get("guardian_reason") or "",
        "curriculum_tier": curriculum.get("tier", 0),
        "curriculum_wins": curriculum.get("wins", 0),
        "curriculum_losses": curriculum.get("losses", 0),
        "curriculum_event": curriculum.get("last_event"),
        "experience_pass": pass_n,
        "experience_fail": fail_n,
        "recent_pass": [
            {
                "title": (r.get("objective") or "")[:60],
                "conf": r.get("confidence"),
                "strategy": r.get("strategy"),
            }
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
        "dataset_pass_rate": dataset.get("pass_rate"),
        "ablation_delta": ablation.get("delta_pass_rate"),
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
    live = {}
    try:
        from core.progress import read_progress

        live = read_progress() or {}
    except Exception:
        live = _read_json(ROOT / "memory" / "runs" / "in_progress.json") or {}

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
    try:
        return _collect_snapshot_inner()
    except Exception as e:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project": "@ETHER",
            "error": str(e),
            "summary": {},
            "intelligence": {},
            "matrix_steps": [],
            "runs": [],
            "gems": GEMS,
            "workflow": WORKFLOW,
            "connections": _sandbox_info(),
        }


def _collect_snapshot_inner() -> Dict[str, Any]:
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
    intel = _intel_block()
    sb = _sandbox_info()

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
                    "verification_score": data.get("verification_score"),
                    "started_at": data.get("started_at"),
                    "retries": data.get("retries", 0),
                    "strategy": data.get("strategy"),
                    "reward": data.get("reward"),
                    "used_burst": data.get("used_burst"),
                    "stages": [
                        {
                            "stage": s.get("stage"),
                            "success": s.get("success"),
                            "detail": (s.get("detail") or "")[:80],
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
    ledger = intel.get("ledger") or {}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": "@ETHER",
        "version": "0.4.0",
        "heartbeat": heartbeat or None,
        "current_work": current_work,
        "intelligence": intel,
        "ledger": ledger,
        "summary": {
            "quality_pass": (latest or {}).get("ok"),
            "confidence": gates.get("confidence"),
            "audit": gates.get("audit_approved"),
            "reason": gates.get("agentic_reason") or gates.get("reason") or "",
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
            "sandbox_backend": sb.get("effective"),
        },
        "workflow": WORKFLOW,
        "matrix_steps": [
            {
                "name": k,
                "ok": v.get("ok"),
                "ms": int((v.get("duration_s") or 0) * 1000),
                "error": (
                    v.get("error_brief")
                    or (("healed:" + str(v["healed"])) if v.get("healed") else "")
                )[:160],
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
            {"name": "curriculum", "status": f"tier {intel.get('curriculum_tier', 0)}", "tip": "Harder tasks after verified wins"},
            {"name": "experience vault", "status": f"{intel.get('experience_pass', 0)} pass / {intel.get('experience_fail', 0)} fail", "tip": "Few-shot + repair bias"},
            {"name": "bench guardian", "status": "FROZEN" if intel.get("guardian_frozen") else "ok", "tip": "Blocks fabricate when bench collapses"},
            {"name": "sandbox", "status": str(sb.get("effective")), "tip": "docker or local subprocess"},
            {"name": "burst", "status": f"calls {ledger.get('burst_ledger_calls', 0)}", "tip": "Frontier only on policy"},
            {"name": "flywheel", "status": "active" if heartbeat else "idle", "tip": "Autonomy loop heartbeat"},
        ],
        "benchmarks": {
            "primary": "bench_pass_rate",
            "pass_rate": intel.get("pass_rate"),
            "quiz_pass_rate": intel.get("quiz_pass_rate"),
            "dataset_pass_rate": intel.get("dataset_pass_rate"),
            "ablation_delta": intel.get("ablation_delta"),
            "pass_rate_avg7": intel.get("pass_rate_avg7"),
            "healthy": intel.get("healthy"),
            "unhealthy_reasons": intel.get("unhealthy_reasons") or [],
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
            "sandbox": sb,
        },
        "policy": {
            "min_confidence": float(os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7") or 0.7),
            "max_retries": int(os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3") or 3),
            "interval_s": int(os.getenv("ETHER_FLYWHEEL_INTERVAL", "900") or 900),
            "push": os.getenv("ETHER_FLYWHEEL_PUSH", "0") == "1",
            "curriculum": os.getenv("ETHER_CURRICULUM", "1") == "1",
            "experience": os.getenv("ETHER_EXPERIENCE", "1") == "1",
            "guardian": os.getenv("ETHER_BENCH_GUARDIAN", "1") == "1",
            "burst_on_fail": os.getenv("ETHER_BURST_ON_FAIL", "1") == "1",
            "sandbox_backend": sb.get("configured"),
        },
        "docs": {
            "status": _read_text(ROOT / "STATUS.md")[:2000],
            "onboarding": _read_text(ROOT / "ONBOARDING.md")[:1200],
            "scoreboard": _read_text(ROOT / "SCOREBOARD.md")[:2000],
        },
        "latest": latest,
        "last_fail": last_fail,
    }
