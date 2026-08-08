"""Collect host_agent job queue, logs, foreman, apprentice lessons, RLHF.

Path rule (non-negotiable): read what host_agent writes under artifacts/.
Never rely on memory/ for remote observability — it is gitignored.
Prefer artifacts/ mirrors for foreman/lessons; fall back only with note.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"
# host_agent writes these under artifacts/ (tracked + pushed)
LOG = ROOT / "artifacts" / "host_agent_log.txt"
STATUS = ROOT / "artifacts" / "host_agent_status.json"
LAST_JOB = ROOT / "artifacts" / "host_agent_last_job.json"
REPORT_MD = ROOT / "artifacts" / "host_report_latest.md"
REPORT_JSON = ROOT / "artifacts" / "host_report_latest.json"
# Prefer artifacts mirrors (path rule); fall back to memory/ with explicit note
FOREMAN_ARTIFACTS = ROOT / "artifacts" / "foreman_state.json"
FOREMAN_MEMORY = ROOT / "memory" / "host_agent" / "foreman_state.json"
LESSONS_ARTIFACTS = ROOT / "artifacts" / "lessons"
LESSONS_MEMORY = ROOT / "memory" / "ether_apprentice" / "lessons"
STATUS_MD = ROOT / "STATUS.md"
PREF_SUMMARY = ROOT / "artifacts" / "preference_summary.json"
STRATEGY_STATS = ROOT / "artifacts" / "strategy_stats.json"
ARTIFACTS = ROOT / "artifacts"


def _list_jobs(folder: Path) -> List[Dict[str, Any]]:
    if not folder.exists():
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(
        folder.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True
    ):
        if p.name == ".gitkeep":
            continue
        item: Dict[str, Any] = {
            "id": p.stem,
            "name": p.name,
            "mtime": datetime.fromtimestamp(
                p.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
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


def _lessons_summary() -> tuple[List[Dict[str, str]], str]:
    """Prefer artifacts/lessons; fall back to memory/ with source note."""
    source = "none"
    folder = None
    if LESSONS_ARTIFACTS.exists() and any(LESSONS_ARTIFACTS.glob("*.json")):
        folder = LESSONS_ARTIFACTS
        source = "artifacts"
    elif LESSONS_MEMORY.exists():
        folder = LESSONS_MEMORY
        source = "memory_fallback"
    if folder is None:
        return [], source
    out: List[Dict[str, str]] = []
    for p in sorted(folder.glob("*.json")):
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
    return out, source


def _foreman_state() -> tuple[Dict[str, Any], str]:
    """Prefer artifacts/foreman_state.json; fall back to memory/ with note."""
    if FOREMAN_ARTIFACTS.exists():
        return _read_json(FOREMAN_ARTIFACTS), "artifacts"
    if FOREMAN_MEMORY.exists():
        return _read_json(FOREMAN_MEMORY), "memory_fallback"
    return {}, "none"


def _phase1_board() -> Dict[str, str]:
    """Parse STATUS.md package table for live Phase 1 board."""
    text = _read_text(STATUS_MD, limit=8000)
    board = {
        "1A": "unknown",
        "1B": "unknown",
        "1C": "unknown",
        "1D": "unknown",
    }
    for line in text.splitlines():
        if "1A Tool-first" in line or "1A Tool-first default" in line:
            if "LANDED" in line:
                board["1A"] = "LANDED"
            elif "NEXT" in line:
                board["1A"] = "NEXT"
            elif "IN PROGRESS" in line:
                board["1A"] = "IN PROGRESS"
        elif "1B AgentState" in line:
            if "WIRED" in line or "LANDED" in line:
                board["1B"] = "WIRED"
            elif "QUEUED" in line:
                board["1B"] = "QUEUED"
        elif "1C AST" in line:
            if "QUEUED" in line:
                board["1C"] = "QUEUED"
            elif "LANDED" in line:
                board["1C"] = "LANDED"
        elif "1D Expand" in line:
            if "IN PROGRESS" in line:
                board["1D"] = "IN PROGRESS"
            elif "LANDED" in line:
                board["1D"] = "LANDED"
            elif "QUEUED" in line:
                board["1D"] = "QUEUED"
    return board


def _rlhf_block() -> Dict[str, Any]:
    """Preference summary + strategy stats for remote RLHF observability."""
    pref = _read_json(PREF_SUMMARY)
    stats = _read_json(STRATEGY_STATS)
    ranked = pref.get("ranked_boosts") or []
    return {
        "n_preferences": pref.get("n_preferences"),
        "n_episodes": pref.get("n_episodes") or stats.get("n_episodes"),
        "updated": pref.get("updated") or stats.get("updated"),
        "rlhf": pref.get("rlhf"),
        "teacher": pref.get("teacher"),
        "ranked_boosts": ranked[:8],
        "strategies": pref.get("strategies") or stats.get("strategies") or {},
        "healthy": bool(pref.get("n_preferences")) and not pref.get("error"),
        "source": "artifacts/preference_summary.json",
    }


def _recent_scoreboards(limit: int = 8) -> List[Dict[str, Any]]:
    """Recent scoreboard_*.json under artifacts/ (mtime desc)."""
    if not ARTIFACTS.exists():
        return []
    files = sorted(
        ARTIFACTS.glob("scoreboard*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out: List[Dict[str, Any]] = []
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            summary = data.get("summary") or {}
            item = {
                "id": p.stem,
                "name": p.name,
                "mtime": datetime.fromtimestamp(
                    p.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
                "passed": summary.get("passed"),
                "total": summary.get("total"),
                "mode": summary.get("mode"),
                "arms": summary.get("arms"),
                "model": summary.get("model"),
            }
            out.append(item)
        except Exception:
            out.append({"id": p.stem, "name": p.name, "error": "parse"})
    return out


def _critique_backlog(limit: int = 12) -> List[Dict[str, Any]]:
    """Open critiques: artifacts/critique_*.json or artifacts/critiques/."""
    paths: List[Path] = []
    if ARTIFACTS.exists():
        paths.extend(ARTIFACTS.glob("critique_*.json"))
        crit_dir = ARTIFACTS / "critiques"
        if crit_dir.exists():
            paths.extend(crit_dir.glob("critique_*.json"))
            paths.extend(crit_dir.glob("*.json"))
    paths = sorted(set(paths), key=lambda p: p.stat().st_mtime, reverse=True)
    out: List[Dict[str, Any]] = []
    for p in paths[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(
                {
                    "id": p.stem,
                    "name": p.name,
                    "mtime": datetime.fromtimestamp(
                        p.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "root_cause": data.get("root_cause"),
                    "confidence": data.get("confidence"),
                    "smallest_experiment": str(
                        data.get("smallest_experiment") or ""
                    )[:180],
                    "job_id": data.get("job_id") or data.get("fail_job_id"),
                }
            )
        except Exception:
            out.append({"id": p.stem, "name": p.name, "error": "parse"})
    return out


def collect_host_agent() -> Dict[str, Any]:
    pending = _list_jobs(PENDING)
    done = _list_jobs(DONE)
    failed = _list_jobs(FAILED)
    status = _read_json(STATUS)
    last = _read_json(LAST_JOB)
    report = _read_json(REPORT_JSON)
    report_md = _read_text(REPORT_MD)
    foreman, foreman_src = _foreman_state()
    lessons, lessons_src = _lessons_summary()
    rlhf = _rlhf_block()
    scoreboards = _recent_scoreboards()
    critiques = _critique_backlog()

    agent_alive = False
    if status.get("heartbeat"):
        try:
            hb = datetime.fromisoformat(
                status["heartbeat"].replace("Z", "+00:00")
            )
            age = (datetime.now(timezone.utc) - hb).total_seconds()
            agent_alive = age < 90
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
        "foreman_source": foreman_src,
        "apprentice": {
            "teacher": "grok",
            "lessons": lessons,
            "n": len(lessons),
            "source": lessons_src,
        },
        "phase1": _phase1_board(),
        "rlhf": rlhf,
        "scoreboards": scoreboards,
        "critiques": critiques,
        "paths": {
            "status": str(STATUS.relative_to(ROOT)),
            "log": str(LOG.relative_to(ROOT)),
            "last_job": str(LAST_JOB.relative_to(ROOT)),
            "pref_summary": str(PREF_SUMMARY.relative_to(ROOT)),
            "foreman_source": foreman_src,
            "lessons_source": lessons_src,
        },
    }
