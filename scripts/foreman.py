"""ETHER Foreman — curriculum + steady + AUTO rate-climb under wheels.

2026-08-22: When curriculum exhausted and honest_rate_eligible < 0.99,
call core.auto_rate_climb.maybe_enqueue so the host keeps climbing
without chat. Skills cannot run on the host — this code does.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"
FAILED_ARCH = ROOT / "artifacts" / "jobs" / "failed_archived"
STATE = ROOT / "memory" / "host_agent" / "foreman_state.json"
STATE_ARTIFACTS = ROOT / "artifacts" / "foreman_state.json"
LAST_JOB = ROOT / "artifacts" / "host_agent_last_job.json"
LESSONS_MEMORY = ROOT / "memory" / "ether_apprentice" / "lessons"
LESSONS_ARTIFACTS = ROOT / "artifacts" / "lessons"

BATCH_SIZE = 6
LIVE_SKIP_TICKS = 36

CURRICULUM: List[Dict[str, Any]] = [
    {
        "id": "p1_01_ruff_tests",
        "note": "P1 ruff + tool_runtime tests",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_ruff_gate.py", "tests/test_tool_runtime.py", "-q", "--tb=line"], "timeout": 300}],
    },
    {
        "id": "p1_02_hard_scripted",
        "note": "P1 hard scripted 5/5",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "scripts.batch_phase_d", "--arm", "direct", "--mode", "scripted", "--tier", "hard"], "timeout": 300}],
    },
    {
        "id": "p2_01_cq_oracle",
        "note": "P2 CQ multifile + repo oracle",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_clear_quartz_multifile.py", "tests/test_repo_oracle.py", "tests/test_repo_oracle_hook.py", "tests/test_repo_oracle_gate.py", "-q", "--tb=line"], "timeout": 300}],
    },
    {
        "id": "p2_02_pipeline_import",
        "note": "P2 pipeline import smoke",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-c", "from core.pipeline import Pipeline; from core.tool_runtime import TOOL_SPECS; assert 'apply_patch' in {t['name'] for t in TOOL_SPECS}; print('ok', len(TOOL_SPECS))"], "timeout": 60}],
    },
    {
        "id": "p3_01_prompt_holdout",
        "note": "P3 prompt_guard + holdout",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_prompt_guard.py", "tests/test_holdout.py", "-q", "--tb=line"], "timeout": 300}],
    },
    {
        "id": "p5_01_patch_multifile",
        "note": "P5 tool_runtime + multifile",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_tool_runtime.py", "tests/test_clear_quartz_multifile.py", "-q", "--tb=line"], "timeout": 300}],
    },
    {
        "id": "p5_02_phase_f_scripted",
        "note": "P5 phase F scripted",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "scripts.batch_phase_f", "--arm", "direct", "--mode", "scripted"], "timeout": 300}],
    },
    {
        "id": "p1_03_expand_repo_oracle",
        "note": "P1 expand + re-verify repo-oracle suite",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_repo_oracle.py", "tests/test_repo_oracle_hook.py", "tests/test_repo_oracle_gate.py", "-q", "--tb=line"], "timeout": 300}],
    },
    {
        "id": "p1_06_ast_transaction_tests",
        "note": "P1 verify Package 1C AST transactional edits",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_ast_transaction.py", "-q", "--tb=short"], "timeout": 120}],
    },
    {
        "id": "p1_07_measure_direct_hard",
        "note": "P1 re-measure direct arm hard pack",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "scripts.batch_phase_d", "--arm", "direct", "--mode", "scripted", "--tier", "hard", "--scoreboard", "artifacts/scoreboard_p1_07_direct.json"], "timeout": 600}],
    },
    {
        "id": "p1_09_train_gates_reverify",
        "note": "P1 doctrine gates + preference health",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_train_gates.py", "tests/test_preference_rlhf.py", "-q", "--tb=line"], "timeout": 180}],
    },
    {
        "id": "p1_10_ast_gate_reverify",
        "note": "P1 AST gate + EditTransaction still green",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_ast_transaction.py", "tests/test_tool_runtime_ast_gate.py", "-q", "--tb=line"], "timeout": 120}],
    },
    {
        "id": "p1_11_direct_hard_rebaseline",
        "note": "P1 continuous direct hard baseline",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "scripts.batch_phase_d", "--arm", "direct", "--mode", "scripted", "--tier", "hard", "--scoreboard", "artifacts/scoreboard_p1_11_direct.json"], "timeout": 600}],
    },
    {
        "id": "p1_12_pipeline_single_ledger",
        "note": "P1 smallest pipeline hyp: ledger + scoreboard",
        "continue_on_fail": True,
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "scripts.batch_phase_d", "--arm", "pipeline", "--mode", "live", "--fixture", "ledger", "--max-steps", "16", "--timeout", "300", "--scoreboard", "artifacts/scoreboard_p1_12_ledger.json"], "timeout": 480}],
    },
]

STEADY_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id_prefix": "ss_measure_tick",
        "note": "steady: measure_tick (rates+snapshot+soft_launch)",
        "class": "measure",
        "continue_on_fail": True,
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "core.measure_tick"], "timeout": 120}],
    },
    {
        "id_prefix": "ss_microbench",
        "note": "steady: microbench_schedule (skip if fresh <5m)",
        "class": "measure",
        "continue_on_fail": True,
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "core.microbench_schedule"], "timeout": 90}],
    },
    {
        "id_prefix": "ss_honest_live_report",
        "note": "steady: publish honest live tool-path rates",
        "class": "measure",
        "continue_on_fail": True,
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "scripts.honest_live_report"], "timeout": 60}],
    },
    {
        "id_prefix": "ss_tool_runtime",
        "note": "steady: tool_runtime + AST gate",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_tool_runtime.py", "tests/test_ast_transaction.py", "-q", "--tb=line"], "timeout": 180}],
    },
    {
        "id_prefix": "ss_train_gates",
        "note": "steady: doctrine + preference integrity",
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "pytest", "tests/test_train_gates.py", "tests/test_preference_rlhf.py", "-q", "--tb=line"], "timeout": 180}],
    },
    {
        "id_prefix": "ss_pipeline_scripted",
        "note": "steady: pipeline scripted (fast 1D signal)",
        "continue_on_fail": True,
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "scripts.batch_phase_d", "--arm", "pipeline", "--mode", "scripted", "--fixture", "ledger", "--max-steps", "16", "--scoreboard", "artifacts/scoreboard_ss_pipeline_scripted.json"], "timeout": 180}],
    },
    {
        "id_prefix": "ss_direct_hard",
        "note": "steady: direct hard baseline",
        "continue_on_fail": True,
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "scripts.batch_phase_d", "--arm", "direct", "--mode", "scripted", "--tier", "hard", "--scoreboard", "artifacts/scoreboard_ss_direct.json"], "timeout": 600}],
    },
    {
        "id_prefix": "ss_archive_failed",
        "note": "steady: archive old failed jobs",
        "continue_on_fail": True,
        "steps": [{"argv": [".venv/Scripts/python.exe", "-m", "scripts.archive_failed"], "timeout": 60}],
    },
    {
        "id_prefix": "ss_pref_refresh",
        "note": "steady: preference + strategy_stats refresh",
        "continue_on_fail": True,
        "steps": [{"argv": [".venv/Scripts/python.exe", "-c",
            "from core.preference import rlhf_tick; import json; print(json.dumps(rlhf_tick(), indent=2))"
        ], "timeout": 180}],
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
        "steady_idx": 0,
        "live_skip_remaining": 0,
        "last_rate_climb_ts": None,
        "rate_climb_idx": 0,
    }


def save_state(state: Dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    state["last_tick"] = _now()
    text = json.dumps(state, indent=2)
    STATE.write_text(text, encoding="utf-8")
    try:
        STATE_ARTIFACTS.parent.mkdir(parents=True, exist_ok=True)
        STATE_ARTIFACTS.write_text(text, encoding="utf-8")
    except Exception:
        pass


def load_lessons() -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for folder in (LESSONS_ARTIFACTS, LESSONS_MEMORY):
        if not folder.exists():
            continue
        for p in sorted(folder.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            lid = str(data.get("id") or p.stem)
            if lid not in by_id:
                by_id[lid] = data
    return list(by_id.values())


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
    job.setdefault("class", "fast")
    path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    return path


def _move_failed_to_done(jid: str) -> bool:
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
    ftype = str(last.get("failure_type") or "").lower()
    hay = (note + " " + str(jid) + " " + ftype).lower()
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
        if (
            "pipeline_ledger" in hay
            or ("pipeline" in hay and "live" in hay)
            or ftype in ("timeout", "live_fail", "budget_exhaust")
            or "tool_runtime_failed_terminal" in hay
        ):
            state["live_skip_remaining"] = LIVE_SKIP_TICKS
            state["last_live_skip_reason"] = jid


def enqueue_steady(state: Dict[str, Any]) -> Optional[str]:
    try:
        from core.queue_governor import may_enqueue_steady, max_enqueue_this_tick

        if not may_enqueue_steady(state):
            return None
        max_n = max_enqueue_this_tick()
    except Exception:
        max_n = 2
        if len(pending_ids()) >= BATCH_SIZE:
            return None
    if max_n <= 0 or not STEADY_TEMPLATES:
        return None
    idx = int(state.get("steady_idx") or 0)
    skip_live = int(state.get("live_skip_remaining") or 0) > 0
    wheels = True
    try:
        import os

        wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    except Exception:
        pass
    enqueued: List[str] = []
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    attempts = 0
    pending = pending_ids()
    while len(enqueued) < max_n and attempts < len(STEADY_TEMPLATES) * 3:
        attempts += 1
        tmpl = STEADY_TEMPLATES[idx % len(STEADY_TEMPLATES)]
        if (skip_live or wheels) and tmpl.get("live"):
            idx += 1
            continue
        jid = f"{tmpl['id_prefix']}_{stamp}_{idx % len(STEADY_TEMPLATES)}"
        if jid in pending or jid in enqueued:
            idx += 1
            continue
        job = {
            "id": jid,
            "note": tmpl.get("note", "steady"),
            "source": "foreman_steady",
            "created": _now(),
            "steps": tmpl["steps"],
            "class": tmpl.get("class") or ("live" if tmpl.get("live") else "fast"),
        }
        if tmpl.get("continue_on_fail"):
            job["continue_on_fail"] = True
        write_job(job)
        enqueued.append(jid)
        idx += 1
    state["steady_idx"] = idx
    state["mode"] = "steady"
    if enqueued:
        state["last_enqueued"] = enqueued[-1]
        return enqueued[-1]
    return None


def enqueue_next(state: Dict[str, Any]) -> Optional[str]:
    pending = pending_ids()
    if len(pending) >= BATCH_SIZE:
        return None
    try:
        from core.queue_governor import may_enqueue

        if not may_enqueue():
            return None
    except Exception:
        pass

    done = set(state.get("completed") or [])
    if DONE.exists():
        for p in DONE.glob("*.json"):
            done.add(p.stem.replace("job_", "") if p.name.startswith("job_") else p.stem)

    cursor = int(state.get("cursor") or 0)
    while cursor < len(CURRICULUM) and CURRICULUM[cursor]["id"] in done:
        cursor += 1
    state["cursor"] = cursor

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
        state["cursor"] = i + 1
        state["last_enqueued"] = jid
        break

    if enqueued:
        return enqueued[-1]

    state["cursor"] = len(CURRICULUM)

    # Host autonomy: rate-climb before steady when honest_rate lags
    try:
        from core.auto_rate_climb import maybe_enqueue as rate_climb

        rc = rate_climb(state, pending=pending_ids(), write_job=write_job)
        if rc:
            return rc
    except Exception as e:
        state["rate_climb_status"] = f"error:{type(e).__name__}:{e}"

    return enqueue_steady(state)


def _is_playbook_recovery(jid: str, note: str) -> bool:
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
    ftype = str(last.get("failure_type") or "unknown")
    hay = f"{note} {jid} {ftype}"
    lessons = load_lessons()
    for les in lessons:
        pat = les.get("match") or ""
        if not pat:
            continue
        if re.search(pat, hay, re.I):
            lid = str(les.get("id") or "unknown")
            try:
                from core.playbook_limiter import allow_playbook, mark_playbook

                if not allow_playbook(ftype, lid):
                    state["last_playbook_skipped"] = f"rate_limit:{lid}:{ftype}"
                    return None
            except Exception:
                pass
            recovery = les.get("enqueue")
            if isinstance(recovery, dict) and recovery.get("id"):
                try:
                    from core.queue_governor import may_enqueue

                    if not may_enqueue():
                        return None
                except Exception:
                    pass
                rid = recovery["id"] + "_" + datetime.now(timezone.utc).strftime("%H%M%S")
                job = {
                    **recovery,
                    "id": rid,
                    "class": recovery.get("class") or "recovery",
                    "note": f"playbook:{les.get('id')} for {jid}",
                }
                write_job(job)
                try:
                    from core.playbook_limiter import mark_playbook

                    mark_playbook(ftype, lid)
                except Exception:
                    pass
                state["last_playbook"] = les.get("id")
                return rid
    return None


def tick() -> Dict[str, Any]:
    state = load_state()
    record_last_job(state)
    recovered = playbook_on_fail(state)
    enqueued = enqueue_next(state)
    skip = int(state.get("live_skip_remaining") or 0)
    if skip > 0:
        state["live_skip_remaining"] = skip - 1
    lessons = load_lessons()
    state["lessons_loaded"] = len(lessons)
    try:
        from core.queue_governor import status_snapshot

        state["governor"] = status_snapshot()
    except Exception:
        pass
    save_state(state)
    try:
        from scripts.write_whats_next import main as _wn

        _wn()
    except Exception:
        pass
    return {
        "enqueued": enqueued,
        "playbook": recovered,
        "cursor": state.get("cursor"),
        "completed_n": len(state.get("completed") or []),
        "lessons": len(lessons),
        "batch_size": BATCH_SIZE,
        "mode": state.get("mode"),
        "rate_climb_status": state.get("rate_climb_status"),
        "live_skip_remaining": state.get("live_skip_remaining", 0),
        "governor": state.get("governor"),
        "state": state,
    }


def status() -> Dict[str, Any]:
    state = load_state()
    rate = None
    try:
        from core.auto_rate_climb import read_honest_rate

        rate = read_honest_rate()
    except Exception:
        pass
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
        "steady_idx": state.get("steady_idx"),
        "live_skip_remaining": state.get("live_skip_remaining", 0),
        "honest_rate_eligible": rate,
        "last_rate_climb_ts": state.get("last_rate_climb_ts"),
        "rate_climb_status": state.get("rate_climb_status"),
    }


if __name__ == "__main__":
    print(json.dumps(tick(), indent=2))
