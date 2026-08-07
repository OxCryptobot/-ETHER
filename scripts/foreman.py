"""ETHER Foreman — advances the job queue without chat babysitting.

Reads apprentice lessons + blueprint cursor. On idle, enqueues next work.
On FAIL, applies playbook requeue when a lesson matches.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"
STATE = ROOT / "memory" / "host_agent" / "foreman_state.json"
LAST_JOB = ROOT / "artifacts" / "host_agent_last_job.json"
LESSONS = ROOT / "memory" / "ether_apprentice" / "lessons"

# Ordered curriculum — foreman walks this when queue empty
CURRICULUM: List[Dict[str, Any]] = [
    {
        "id": "p1_01_ruff_tests",
        "note": "P1 ruff + tool_runtime tests",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_ruff_gate.py",
                    "tests/test_tool_runtime.py",
                    "-q",
                    "--tb=line",
                ],
                "timeout": 300,
            }
        ],
    },
    {
        "id": "p1_02_hard_scripted",
        "note": "P1 hard scripted 5/5",
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
                    "--tier",
                    "hard",
                ],
                "timeout": 300,
            }
        ],
    },
    {
        "id": "p2_01_cq_oracle",
        "note": "P2 CQ multifile + repo oracle",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_clear_quartz_multifile.py",
                    "tests/test_repo_oracle.py",
                    "tests/test_repo_oracle_hook.py",
                    "tests/test_repo_oracle_gate.py",
                    "-q",
                    "--tb=line",
                ],
                "timeout": 300,
            }
        ],
    },
    {
        "id": "p2_02_pipeline_import",
        "note": "P2 pipeline import smoke",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-c",
                    "from core.pipeline import Pipeline; from core.tool_runtime import TOOL_SPECS; assert 'apply_patch' in {t['name'] for t in TOOL_SPECS}; print('ok', len(TOOL_SPECS))",
                ],
                "timeout": 60,
            }
        ],
    },
    {
        "id": "p3_01_prompt_holdout",
        "note": "P3 prompt_guard + holdout",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_prompt_guard.py",
                    "tests/test_holdout.py",
                    "-q",
                    "--tb=line",
                ],
                "timeout": 300,
            }
        ],
    },
    {
        "id": "p5_01_patch_multifile",
        "note": "P5 tool_runtime + multifile",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_tool_runtime.py",
                    "tests/test_clear_quartz_multifile.py",
                    "-q",
                    "--tb=line",
                ],
                "timeout": 300,
            }
        ],
    },
    {
        "id": "p5_02_phase_f_scripted",
        "note": "P5 phase F scripted",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "scripts.batch_phase_f",
                    "--arm",
                    "direct",
                    "--mode",
                    "scripted",
                ],
                "timeout": 300,
            }
        ],
    },
    {
        "id": "z_gate_pytest_core",
        "note": "Gate core pytest",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_tool_runtime.py",
                    "tests/test_ruff_gate.py",
                    "tests/test_repo_oracle.py",
                    "-q",
                    "--tb=line",
                ],
                "timeout": 300,
            }
        ],
    },
    {
        "id": "z_gate_hard_scripted",
        "note": "Gate hard scripted",
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
                    "--tier",
                    "hard",
                ],
                "timeout": 300,
            }
        ],
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> Dict[str, Any]:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "cursor": 0,
        "completed": [],
        "failed": [],
        "last_tick": None,
        "mode": "apprentice",
        "teacher": "grok",
    }


def save_state(state: Dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    state["last_tick"] = _now()
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_lessons() -> List[Dict[str, Any]]:
    LESSONS.mkdir(parents=True, exist_ok=True)
    out: List[Dict[str, Any]] = []
    for p in sorted(LESSONS.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def pending_ids() -> set:
    PENDING.mkdir(parents=True, exist_ok=True)
    return {p.stem.replace("job_", "") if p.name.startswith("job_") else p.stem for p in PENDING.glob("*.json") if p.name != ".gitkeep"}


def write_job(job: Dict[str, Any]) -> Path:
    PENDING.mkdir(parents=True, exist_ok=True)
    jid = job["id"]
    path = PENDING / f"{jid}.json"
    job = dict(job)
    job.setdefault("created", _now())
    job.setdefault("source", "foreman")
    path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    return path


def record_last_job(state: Dict[str, Any]) -> None:
    if not LAST_JOB.exists():
        return
    try:
        last = json.loads(LAST_JOB.read_text(encoding="utf-8"))
    except Exception:
        return
    jid = last.get("job_id")
    if not jid:
        return
    if last.get("ok") is True:
        if jid not in state["completed"]:
            state["completed"].append(jid)
        state["failed"] = [x for x in state.get("failed", []) if x != jid]
    elif last.get("ok") is False:
        if jid not in state.get("failed", []):
            state.setdefault("failed", []).append(jid)


def enqueue_next(state: Dict[str, Any]) -> Optional[str]:
    """If pending empty, place next curriculum job not yet completed."""
    if pending_ids():
        return None
    done = set(state.get("completed") or [])
    # also treat files in done/ as completed
    if DONE.exists():
        for p in DONE.glob("*.json"):
            done.add(p.stem.replace("job_", "") if p.name.startswith("job_") else p.stem)

    cursor = int(state.get("cursor") or 0)
    for i, item in enumerate(CURRICULUM):
        if i < cursor:
            continue
        jid = item["id"]
        if jid in done:
            state["cursor"] = i + 1
            continue
        write_job(item)
        state["cursor"] = i
        state["last_enqueued"] = jid
        return jid
    # loop continuous gates at end
    for item in CURRICULUM:
        if item["id"].startswith("z_gate_"):
            write_job({**item, "id": item["id"] + "_" + datetime.now(timezone.utc).strftime("%H%M%S")})
            state["last_enqueued"] = item["id"]
            return item["id"]
    return None


def playbook_on_fail(state: Dict[str, Any]) -> Optional[str]:
    """Match apprentice lessons against last failure; enqueue recovery job."""
    if not LAST_JOB.exists():
        return None
    try:
        last = json.loads(LAST_JOB.read_text(encoding="utf-8"))
    except Exception:
        return None
    if last.get("ok") is not False:
        return None
    jid = last.get("job_id") or ""
    note = (last.get("note") or "") + " " + jid
    lessons = load_lessons()
    for les in lessons:
        pat = les.get("match") or ""
        if not pat:
            continue
        if re.search(pat, note, re.I) or re.search(pat, jid, re.I):
            recovery = les.get("enqueue")
            if isinstance(recovery, dict) and recovery.get("id"):
                rid = recovery["id"] + "_" + datetime.now(timezone.utc).strftime("%H%M%S")
                job = {**recovery, "id": rid, "note": f"playbook:{les.get('id')} for {jid}"}
                write_job(job)
                state["last_playbook"] = les.get("id")
                return rid
    return None


def tick() -> Dict[str, Any]:
    """One foreman cycle. Call from ether_host after jobs or on idle."""
    state = load_state()
    record_last_job(state)
    recovered = playbook_on_fail(state)
    enqueued = enqueue_next(state)
    lessons = load_lessons()
    state["lessons_loaded"] = len(lessons)
    save_state(state)
    return {
        "enqueued": enqueued,
        "playbook": recovered,
        "cursor": state.get("cursor"),
        "completed_n": len(state.get("completed") or []),
        "lessons": len(lessons),
        "state": state,
    }


def status() -> Dict[str, Any]:
    state = load_state()
    return {
        "cursor": state.get("cursor"),
        "completed": state.get("completed") or [],
        "failed": state.get("failed") or [],
        "last_enqueued": state.get("last_enqueued"),
        "last_playbook": state.get("last_playbook"),
        "lessons": len(load_lessons()),
        "curriculum_len": len(CURRICULUM),
        "pending": sorted(pending_ids()),
        "mode": state.get("mode", "apprentice"),
        "teacher": state.get("teacher", "grok"),
        "last_tick": state.get("last_tick"),
    }


if __name__ == "__main__":
    print(json.dumps(tick(), indent=2))
