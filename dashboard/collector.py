"""Collect live system state for the dashboard."""

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
    {"id": "clear-quartz", "role": "Sandbox execution", "layer": "verify"},
    {"id": "rose-quartz", "role": "LLM router", "layer": "generate"},
    {"id": "citrine", "role": "Workspace memory", "layer": "memory"},
    {"id": "selenite", "role": "Planner", "layer": "plan"},
    {"id": "amethyst", "role": "Learning log", "layer": "learn"},
    {"id": "black-tourmaline", "role": "Security audit", "layer": "verify"},
    {"id": "labradorite", "role": "Critique / profile", "layer": "review"},
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


def _parse_tasks(md: str) -> Dict[str, Any]:
    batches: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    row_re = re.compile(
        r"^\|\s*(\d+)\s*\|\s*([^|]*?)\s*\|\s*([^|]+?)\s*\|(?:\s*([^|]*?)\s*\|)?\s*$"
    )
    lines = md.splitlines()
    section = "unknown"
    for line in lines:
        sm = re.match(r"^##\s+(.+)$", line.strip())
        if sm:
            section = sm.group(1).strip()
            if "batch" in section.lower() or "done" in section.lower() or "active" in section.lower() or "p0" in section.lower():
                current = {"name": section, "tasks": []}
                batches.append(current)
            continue
        m = row_re.match(line.strip())
        if not m or current is None:
            continue
        num, col2, col3, col4 = m.group(1), m.group(2).strip(), m.group(3).strip(), (m.group(4) or "").strip()
        if not num.isdigit():
            continue
        status = "queued"
        priority = ""
        title = col2
        notes = col3
        if "done" in section.lower() or "**done**" in col3.lower() or col3.lower() == "done":
            status = "done"
            title = col2
            notes = col3
        elif "active" in section.lower() or "next" in section.lower() or "batch 3" in section.lower():
            status = "queued"
            priority = col2
            title = col3
            notes = col4
        current["tasks"].append(
            {"id": int(num), "title": title[:120], "status": status, "priority": priority[:8], "notes": notes[:100]}
        )
    all_tasks = [t for b in batches for t in b["tasks"]]
    done = sum(1 for t in all_tasks if t["status"] == "done")
    queued = sum(1 for t in all_tasks if t["status"] != "done")
    return {
        "batches": batches,
        "totals": {"done": done, "queued": queued, "total": len(all_tasks)},
        "progress_pct": round(100 * done / len(all_tasks), 1) if all_tasks else 0.0,
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

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": "@ETHER",
        "version": "0.1.1",
        "heartbeat": heartbeat or None,
        "current_work": current_work,
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
            "tasks_done": tasks.get("totals", {}).get("done"),
            "tasks_queued": tasks.get("totals", {}).get("queued"),
            "tasks_progress_pct": tasks.get("progress_pct"),
            "pull_error": (steps.get("pull") or {}).get("error_brief")
            or (steps.get("pull") or {}).get("healed"),
        },
        "workflow": [
            {"id": 1, "name": "Pull", "desc": "git fetch + ff-only (self-heal)"},
            {"id": 2, "name": "Static", "desc": "smoke + pytest"},
            {"id": 3, "name": "Plan", "desc": "Selenite"},
            {"id": 4, "name": "Tool assist", "desc": "few_shot + repo_map"},
            {"id": 5, "name": "Code", "desc": "Rose Quartz"},
            {"id": 6, "name": "Sandbox", "desc": "Clear Quartz"},
            {"id": 7, "name": "Audit", "desc": "Black Tourmaline"},
            {"id": 8, "name": "Learn / report", "desc": "Amethyst + git"},
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
            "ranked": bandit_ranked[:8],
            "fail_streak": fail_streak,
        },
        "skills": [
            {"name": "plan → code → sandbox → audit", "status": "active"},
            {"name": "tool_assist + scans", "status": "on" if os.getenv("ETHER_TOOL_ASSIST", "1") == "1" else "off"},
            {"name": "warm sandbox", "status": "on" if os.getenv("ETHER_WARM_SANDBOX", "0") == "1" else "off"},
            {"name": "git reset ok", "status": "on" if os.getenv("ETHER_GIT_RESET_OK", "0") == "1" else "off"},
            {"name": "flywheel autonomy", "status": "active" if heartbeat else "idle"},
            {"name": "fail streak", "status": str(fail_streak.get("streak", 0))},
        ],
        "benchmarks": {
            "flywheel_cycles": len(history),
            "flywheel_pass_rate": round(fw_pass / fw_total, 3) if history else None,
            "pipeline_runs_sampled": len(runs),
            "pipeline_success_rate": round(complete / max(1, complete + errors), 3),
            "avg_confidence": avg_conf,
            "last_fail_reason": ((last_fail or {}).get("gates") or {}).get("agentic_reason"),
        },
        "connections": {
            "docker": shutil.which("docker") is not None,
            "ollama": shutil.which("ollama") is not None,
            "qdrant_url": os.getenv("QDRANT_URL", "http://localhost:6333"),
            "ollama_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            "primary_model": os.getenv("ETHER_PRIMARY_MODEL", ""),
        },
        "policy": {
            "min_confidence": float(os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7")),
            "max_retries": int(os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3")),
            "interval_s": int(os.getenv("ETHER_FLYWHEEL_INTERVAL", "900")),
            "push": os.getenv("ETHER_FLYWHEEL_PUSH", "0") == "1",
            "sandbox_retry": os.getenv("ETHER_SANDBOX_RETRY", "1") == "1",
            "pull_soft": os.getenv("ETHER_PULL_SOFT", "1") == "1",
            "git_reset_ok": os.getenv("ETHER_GIT_RESET_OK", "0") == "1",
        },
        "docs": {
            "status": _read_text(ROOT / "STATUS.md")[:1800],
            "flywheel": _read_text(ROOT / "FLYWHEEL.md")[:1200],
            "tasks": tasks_md[:2500],
        },
        "latest": latest,
        "last_fail": last_fail,
    }
