"""ETHER Foreman — advances the job queue without chat babysitting.

Reads apprentice lessons + blueprint cursor. On idle, enqueues next work.
On FAIL, applies playbook requeue when a lesson matches.

HARD RULE: never apply a playbook to a job that is itself a playbook recovery
(note starts with 'playbook:' or id contains '_diag_after_' / recovery markers).
That produced an infinity loop 2026-08-08.

REVAMP 2026-08-08:
- Sequential batch fill (BATCH_SIZE under training wheels) so queue can hold next N
  curriculum items in order when idle. Host still drains FIFO back-to-back.
- On successful playbook recovery, convert the original failed job file to done/
  (recovered). Does not hide root cause; only after a recovery PASS.
- Curriculum expanded with remaining Phase 1 items only. Continuous z_gate still
  DISABLED. Training wheels stay ON until measured lift + Phase 1 gate green.

2026-08-14: added p1_04b / p1_06 / p1_07 / p1_08 for AST verification +
measurement follow-ups after Package 1C landed.

2026-08-14 (steady flow): BATCH_SIZE raised to 10 so foreman keeps a constant
pending depth for continuous learning. Failed jobs are converted into
Labradorite critiques + lessons + smallest experiments (never blind re-run).
"""
from __future__ import annotations

import json
import os
import re
import shutil
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

# Steady workflow: keep ~10 jobs in pending so the host never idles while
# Phase 1 measurement + learning from FAILs is open. Training wheels still ON.
BATCH_SIZE = 10

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
    # --- Phase 1 remaining (gate work only; do not advance to Phase 2+ until green) ---
    {
        "id": "p1_03_expand_repo_oracle",
        "note": "P1 expand + re-verify repo-oracle suite (≥10 hard path)",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
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
        "id": "p1_04_measure_pipeline_lift",
        "note": "P1 measure pipeline vs direct lift on hard pack (scoreboard)",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "scripts.batch_phase_d",
                    "--arm",
                    "pipeline",
                    "--mode",
                    "scripted",
                    "--tier",
                    "hard",
                ],
                "timeout": 600,
            }
        ],
    },
    {
        "id": "p1_05_labradorite_remaining",
        "note": "P1 Labradorite critique on remaining non-infra FAILs (one hyp)",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "core.evolution_loop",
                ],
                "timeout": 300,
            }
        ],
    },
    # --- 2026-08-14 additions after Package 1C landed ---
    {
        "id": "p1_04b_measure_pipeline_lift_verbose",
        "note": "P1 follow-up: pipeline hard pack with explicit scoreboard (Labradorite after p1_04)",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "scripts.batch_phase_d",
                    "--arm",
                    "pipeline",
                    "--mode",
                    "scripted",
                    "--tier",
                    "hard",
                    "--timeout",
                    "480",
                    "--scoreboard",
                    "artifacts/scoreboard_p1_04b.json",
                ],
                "timeout": 900,
            }
        ],
    },
    {
        "id": "p1_06_ast_transaction_tests",
        "note": "P1 verify Package 1C AST transactional edits",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_ast_transaction.py",
                    "-q",
                    "--tb=short",
                ],
                "timeout": 120,
            }
        ],
    },
    {
        "id": "p1_07_measure_direct_hard",
        "note": "P1 re-measure direct arm hard pack (baseline for lift)",
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
                    "--timeout",
                    "400",
                    "--scoreboard",
                    "artifacts/scoreboard_p1_07_direct.json",
                ],
                "timeout": 600,
            }
        ],
    },
    {
        "id": "p1_08_expand_hard_count",
        "note": "P1 confirm hard fixture count + repo-oracle gate (toward ≥10)",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_repo_oracle.py",
                    "tests/test_repo_oracle_gate.py",
                    "tests/test_repo_oracle_hook.py",
                    "-q",
                    "--tb=line",
                ],
                "timeout": 300,
            }
        ],
    },
    # --- Steady learning stream (keep queue full while measuring lift) ---
    {
        "id": "p1_09_train_gates_reverify",
        "note": "P1 doctrine gates + preference health (learning integrity)",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_train_gates.py",
                    "tests/test_preference_rlhf.py",
                    "-q",
                    "--tb=line",
                ],
                "timeout": 180,
            }
        ],
    },
    {
        "id": "p1_10_ast_gate_reverify",
        "note": "P1 AST gate + EditTransaction still green",
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_ast_transaction.py",
                    "tests/test_tool_runtime_ast_gate.py",
                    "-q",
                    "--tb=line",
                ],
                "timeout": 120,
            }
        ],
    },
    {
        "id": "p1_11_direct_hard_rebaseline",
        "note": "P1 continuous direct hard baseline for lift comparison",
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
                    "--scoreboard",
                    "artifacts/scoreboard_p1_11_direct.json",
                ],
                "timeout": 600,
            }
        ],
    },
    {
        "id": "p1_12_pipeline_single_ledger",
        "note": "P1 smallest pipeline hyp: single hard fixture (ledger) + scoreboard",
        "continue_on_fail": True,
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "scripts.batch_phase_d",
                    "--arm",
                    "pipeline",
                    "--mode",
                    "live",
                    "--fixture",
                    "ledger",
                    "--max-steps",
                    "16",
                    "--timeout",
                    "400",
                    "--scoreboard",
                    "artifacts/scoreboard_p1_12_ledger.json",
                ],
                "timeout": 600,
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
    return {
        p.stem.replace("job_", "") if p.name.startswith("job_") else p.stem
        for p in PENDING.glob("*.json")
        if p.name != ".gitkeep"
    }


def write_job(job: Dict[str, Any]) -> Path:
    PENDING.mkdir(parents=True, exist_ok=True)
    jid = job["id"]
    path = PENDING / f"{jid}.json"
    job = dict(job)
    job.setdefault("created", _now())
    job.setdefault("source", "foreman")
    path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    return path


def _move_failed_to_done(jid: str) -> bool:
    """Convert a recovered failed job to done/ (file move). Returns True if moved."""
    src = FAILED / f"{jid}.json"
    if not src.exists():
        for p in FAILED.glob(f"*{jid}*.json"):
            src = p
            break
        else:
            return False
    DONE.mkdir(parents=True, exist_ok=True)
    dst = DONE / src.name
    try:
        shutil.move(str(src), str(dst))
        return True
    except Exception:
        return False


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
    note = last.get("note") or ""
    if last.get("ok") is True:
        if jid not in state["completed"]:
            state["completed"].append(jid)
        state["failed"] = [x for x in state.get("failed", []) if x != jid]
        if note.strip().lower().startswith("playbook:"):
            m = re.search(r"for\s+([\w\-\.]+)", note, re.I)
            if m:
                orig = m.group(1).strip()
                if _move_failed_to_done(orig):
                    if orig not in state["completed"]:
                        state["completed"].append(orig)
                    state["failed"] = [x for x in state.get("failed", []) if x != orig]
                    state["last_converted"] = orig
    elif last.get("ok") is False:
        if jid not in state.get("failed", []):
            state.setdefault("failed", []).append(jid)


def enqueue_next(state: Dict[str, Any]) -> Optional[str]:
    """Enqueue up to BATCH_SIZE next unfinished curriculum items in sequential order.

    Returns the last id enqueued (or None). Host drains FIFO so order is preserved.
    Continuous loop remains disabled: stops when curriculum is exhausted.
    """
    pending = pending_ids()
    if len(pending) >= BATCH_SIZE:
        return None

    done = set(state.get("completed") or [])
    if DONE.exists():
        for p in DONE.glob("*.json"):
            done.add(p.stem.replace("job_", "") if p.name.startswith("job_") else p.stem)

    cursor = int(state.get("cursor") or 0)
    enqueued: List[str] = []
    for i, item in enumerate(CURRICULUM):
        if len(pending) + len(enqueued) >= BATCH_SIZE:
            break
        if i < cursor:
            continue
        jid = item["id"]
        if jid in done or jid in pending or jid in enqueued:
            state["cursor"] = i + 1
            continue
        write_job(item)
        enqueued.append(jid)
        state["cursor"] = i
        state["last_enqueued"] = jid

    if not enqueued:
        state["cursor"] = len(CURRICULUM)
        return None
    return enqueued[-1]


def _is_playbook_recovery(jid: str, note: str) -> bool:
    """True if this failure is already a playbook recovery — do not chain."""
    n = (note or "").strip().lower()
    j = (jid or "").strip().lower()
    if n.startswith("playbook:"):
        return True
    if "diag_after_budget" in j or "diag_after_budget" in n:
        return True
    if j.startswith("phase_e_ledger_trace") or j.startswith("phase_e_topo_trace"):
        return True
    return False


def playbook_on_fail(state: Dict[str, Any]) -> Optional[str]:
    """Match apprentice lessons against last failure; enqueue recovery job once."""
    if not LAST_JOB.exists():
        return None
    try:
        last = json.loads(LAST_JOB.read_text(encoding="utf-8"))
    except Exception:
        return None
    if last.get("ok") is not False:
        return None
    jid = last.get("job_id") or ""
    note = last.get("note") or ""
    if _is_playbook_recovery(jid, note):
        return None
    hay = note + " " + jid
    lessons = load_lessons()
    for les in lessons:
        pat = les.get("match") or ""
        if not pat:
            continue
        if re.search(pat, hay, re.I):
            recovery = les.get("enqueue")
            if isinstance(recovery, dict) and recovery.get("id"):
                rid = recovery["id"] + "_" + datetime.now(timezone.utc).strftime("%H%M%S")
                job = {
                    **recovery,
                    "id": rid,
                    "note": f"playbook:{les.get('id')} for {jid}",
                }
                write_job(job)
                state["last_playbook"] = les.get("id")
                return rid
    return None


def tick() -> Dict[str, Any]:
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
        "batch_size": BATCH_SIZE,
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
        "last_converted": state.get("last_converted"),
        "lessons": len(load_lessons()),
        "curriculum_len": len(CURRICULUM),
        "batch_size": BATCH_SIZE,
        "pending": sorted(pending_ids()),
        "mode": state.get("mode", "apprentice"),
        "teacher": state.get("teacher", "grok"),
        "last_tick": state.get("last_tick"),
    }


if __name__ == "__main__":
    print(json.dumps(tick(), indent=2))
