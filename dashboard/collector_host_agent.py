"""Collect host_agent job queue, logs, foreman, apprentice lessons."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"
LOG = ROOT / "memory" / "host_agent" / "agent.log"
STATUS = ROOT / "memory" / "host_agent" / "status.json"
LAST_JOB = ROOT / "artifacts" / "host_agent_last_job.json"
REPORT_MD = ROOT / "artifacts" / "host_report_latest.md"
REPORT_JSON = ROOT / "artifacts" / "host_report_latest.json"
FOREMAN_STATE = ROOT / "memory" / "host_agent" / "foreman_state.json"
LESSONS = ROOT / "memory" / "ether_apprentice" / "lessons"


def _list_jobs(folder: Path) -> List[Dict[str, Any]]:
    if not folder.exists():
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(folder.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name == ".gitkeep":
            continue
        item: Dict[str, Any] = {
            "id": p.stem,
            "name": p.name,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            item["sprint"] = data.get("sprint")
            item["note"] = data.get("note")
            item["created"] = data.get("created")
            item["source"] = data.get("source")
        except Exception:
            pass
        out.append(item)
    return out[:40]


def _tail_log(max_lines: int = 120) -> List[str]:
    if not LOG.exists():
        return ["(no agent log yet — start scripts/ether_host.py)"]
    try:
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-max_lines:]
    except Exception as e:
        return [f"(log read error: {e})"]


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e)}


def _read_text(path: Path, limit: int = 12000) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception as e:
        return f"(read error: {e})"


def _lessons_summary() -> List[Dict[str, str]]:
    if not LESSONS.exists():
        return []
    out = []
    for p in sorted(LESSONS.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append(
                {
                    "id": str(d.get("id") or p.stem),
                    "craft": str(d.get("craft") or ""),
                    "rule": str(d.get("rule") or "")[:200],
                }
            )
        except Exception:
            continue
    return out


def collect_host_agent() -> Dict[str, Any]:
    pending = _list_jobs(PENDING)
    done = _list_jobs(DONE)
    failed = _list_jobs(FAILED)
    status = _read_json(STATUS)
    last = _read_json(LAST_JOB)
    report = _read_json(REPORT_JSON)
    report_md = _read_text(REPORT_MD)
    foreman = _read_json(FOREMAN_STATE)
    lessons = _lessons_summary()

    agent_alive = False
    if status.get("heartbeat"):
        try:
            hb = datetime.fromisoformat(status["heartbeat"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - hb).total_seconds()
            agent_alive = age < 60
            status["heartbeat_age_s"] = round(age, 1)
        except Exception:
            pass

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent_alive": agent_alive,
        "status": status,
        "last_job": last,
        "queue": {
            "pending": pending,
            "done": done,
            "failed": failed,
            "counts": {
                "pending": len(pending),
                "done": len(done),
                "failed": len(failed),
            },
        },
        "log_lines": _tail_log(150),
        "report": report,
        "report_md": report_md,
        "foreman": foreman,
        "apprentice": {
            "teacher": "grok",
            "lessons": lessons,
            "n": len(lessons),
        },
    }
