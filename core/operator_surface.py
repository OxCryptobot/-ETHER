"""Operator Surface — single facade for CLI, Control Matrix, and host_agent.

All paths read/write the same artifacts/ that host_agent already owns.
Never lifts training wheels. Never invents a second scoring path.

OS-1: status job test rates chat git tools learn doctor llm
OS-2/3/4: skill upload swarm multifile speech
OS-5 2026-08-22: chat routes through chat_orchestrator (local Ollama + git + escalate)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"
ARCH = ROOT / "artifacts" / "jobs" / "failed_archived"
LESSONS = ROOT / "memory" / "ether_apprentice" / "lessons"
UPLOADS = ROOT / "artifacts" / "uploads"
QUARANTINE = ROOT / "tools" / "quarantine"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def status() -> Dict[str, Any]:
    st = _load(ROOT / "artifacts" / "host_agent_status.json")
    last = _load(ROOT / "artifacts" / "host_agent_last_job.json")
    return {
        "updated": _now(),
        "host": st,
        "last_job": last,
        "pending_n": len(list_jobs("pending")),
        "done_n": len(list_jobs("done")),
        "failed_n": len(list_jobs("failed")),
    }


def list_jobs(kind: str = "pending") -> List[str]:
    folder = {"pending": PENDING, "done": DONE, "failed": FAILED}.get(kind, PENDING)
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if p.name != ".gitkeep")


def enqueue_job(job: Dict[str, Any]) -> Path:
    PENDING.mkdir(parents=True, exist_ok=True)
    job_id = job.get("id") or f"job_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    job = dict(job)
    job["id"] = job_id
    try:
        from core.live_budget import apply_to_job

        job = apply_to_job(job)
    except Exception:
        pass
    path = PENDING / f"{job_id}.json"
    path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    return path


def cancel_job(job_id: str) -> bool:
    src = PENDING / f"{job_id}.json"
    if not src.exists():
        matches = list(PENDING.glob(f"*{job_id}*.json"))
        if not matches:
            return False
        src = matches[0]
    ARCH.mkdir(parents=True, exist_ok=True)
    dst = ARCH / f"{src.stem}_cancelled.json"
    shutil.move(str(src), str(dst))
    return True


def rates() -> Dict[str, Any]:
    out: Dict[str, Any] = {"updated": _now()}
    for name in ("phase1_gate", "eligible_rates", "honest_live_rates", "multi_llm"):
        p = ROOT / "artifacts" / f"{name}.json"
        if p.exists():
            out[name] = _load(p)
    try:
        from core.multi_llm import publish as ml_publish

        out["multi_llm"] = ml_publish()
    except Exception as e:
        out["multi_llm_error"] = str(e)[:160]
    return out


def run_test(
    fixture: str,
    *,
    live: bool = False,
    arm: str = "direct",
    max_steps: int = 8,
    timeout: int = 280,
) -> Path:
    mode = "live" if live else "scripted"
    cls = "gate_sample" if live else "fast"
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    job_id = f"os_test_{fixture}_{mode}_{stamp}"
    sb = f"artifacts/scoreboard_{job_id}.json"
    argv = [
        ".venv/Scripts/python.exe",
        "-m",
        "scripts.batch_phase_d",
        "--mode",
        mode,
        "--fixture",
        fixture,
        "--arm",
        arm,
        "--max-steps",
        str(max_steps),
        "--timeout",
        str(timeout),
        "--scoreboard",
        sb,
    ]
    job = {
        "id": job_id,
        "note": f"operator_surface test {fixture} {mode} arm={arm} — countable",
        "class": cls,
        "continue_on_fail": True,
        "steps": [{"argv": argv, "timeout": timeout + 30}],
    }
    return enqueue_job(job)


def git_sync() -> Dict[str, Any]:
    def run(cmd: List[str], timeout: int = 90) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    run(["git", "fetch", "origin"], timeout=120)
    r = run(["git", "merge", "--ff-only", "origin/main"], timeout=60)
    if r.returncode == 0:
        return {"ok": True, "action": "ff-only", "msg": "up to date or fast-forwarded"}
    run(["git", "rebase", "--abort"], timeout=30)
    run(["git", "merge", "--abort"], timeout=30)
    run(["git", "reset", "--hard", "origin/main"], timeout=60)
    return {"ok": True, "action": "hard_reset", "msg": "diverged — reset to origin/main"}


def chat_post(
    message: str,
    *,
    job_id: Optional[str] = None,
    orchestrate: bool = True,
    allow_write: bool = False,
    force_channel: Optional[str] = None,
) -> Dict[str, Any]:
    """Operator message. Default: full chat orchestrator turn.

    Set orchestrate=False to raw-bus post to Grok only (legacy path).
    """
    if orchestrate:
        try:
            from core.chat_orchestrator import turn

            return turn(
                message,
                job_id=job_id,
                allow_write=allow_write,
                force_channel=force_channel,
            )
        except Exception as e:
            from core.chat_bus import post_operator

            env = post_operator(f"[orchestrator fallback] {message}", job_id=job_id)
            return {
                "ok": False,
                "error": f"orchestrator: {type(e).__name__}: {e}",
                "envelope": env,
                "fallback": True,
            }
    from core.chat_bus import post_operator

    return post_operator(message, job_id=job_id)


def chat_inbox(limit: int = 10) -> List[Dict[str, Any]]:
    from core.chat_bus import receive

    return receive(from_grok=True, limit=limit)


def chat_turns(limit: int = 20) -> List[Dict[str, Any]]:
    try:
        from core.chat_orchestrator import recent_turns

        return recent_turns(limit=limit)
    except Exception:
        return []


def tools_list() -> Dict[str, Any]:
    pers = ROOT / "tools" / "persistent"
    quar = ROOT / "tools" / "quarantine"
    return {
        "persistent": sorted(p.name for p in pers.glob("*.py")) if pers.exists() else [],
        "quarantine": sorted(p.name for p in quar.glob("*.py")) if quar.exists() else [],
    }


def learn_summary() -> Dict[str, Any]:
    out: Dict[str, Any] = {"updated": _now()}
    for name in ("preference_summary", "strategy_stats", "whats_next"):
        p = ROOT / "artifacts" / f"{name}.json"
        if p.exists():
            out[name] = _load(p)
    return out


def doctor() -> Dict[str, Any]:
    issues: List[str] = []
    st = _load(ROOT / "artifacts" / "host_agent_status.json")
    hb = st.get("heartbeat")
    if not hb:
        issues.append("CRITICAL: no host heartbeat")
    else:
        try:
            t = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - t).total_seconds()
            if age > 120:
                issues.append(f"WARNING: heartbeat stale ({age:.0f}s)")
        except Exception:
            issues.append("WARNING: heartbeat unparseable")
    n_failed = len(list_jobs("failed"))
    if n_failed > 20:
        issues.append(f"WARNING: failed queue large ({n_failed})")
    rates_data = rates()
    p1 = rates_data.get("phase1_gate") or {}
    if p1.get("honest_rate_eligible") is not None and p1.get("honest_rate_eligible") < 0.99:
        issues.append(
            f"INFO: honest_rate_eligible={p1.get('honest_rate_eligible')} (target ≥0.99)"
        )
    return {
        "ok": not any(i.startswith("CRITICAL") for i in issues),
        "issues": issues,
        "host_phase": st.get("phase"),
        "pending_n": len(list_jobs("pending")),
    }


def skill_list() -> List[Dict[str, Any]]:
    if not LESSONS.exists():
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(LESSONS.glob("*.json")):
        data = _load(p)
        out.append(
            {
                "id": data.get("id") or p.stem,
                "craft": data.get("craft"),
                "rule": (data.get("rule") or "")[:200],
                "path": str(p.relative_to(ROOT)).replace("\\", "/"),
            }
        )
    return out


def skill_show(skill_id: str) -> Dict[str, Any]:
    if not LESSONS.exists():
        return {"error": "no lessons dir"}
    for p in LESSONS.glob("*.json"):
        data = _load(p)
        if data.get("id") == skill_id or p.stem == skill_id or skill_id in p.stem:
            return data
    return {"error": f"skill not found: {skill_id}"}


def upload_file(
    src_path: str,
    *,
    dest: str = "uploads",
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    src = Path(src_path)
    if not src.is_file():
        return {"ok": False, "error": f"not a file: {src_path}"}
    name = filename or src.name
    if dest == "quarantine":
        target_dir = QUARANTINE
    else:
        target_dir = UPLOADS
    target_dir.mkdir(parents=True, exist_ok=True)
    dst = target_dir / name
    shutil.copy2(src, dst)
    return {
        "ok": True,
        "path": str(dst.relative_to(ROOT)).replace("\\", "/"),
        "bytes": dst.stat().st_size,
    }


def swarm_enqueue(
    note: str = "operator swarm batch",
    *,
    fixtures: Optional[List[str]] = None,
    live: bool = False,
) -> List[Path]:
    fixtures = fixtures or ["wallet", "greeter"]
    paths: List[Path] = []
    for fx in fixtures:
        paths.append(run_test(fx, live=live, arm="direct"))
    return paths


def multifile_job(
    objective: str,
    *,
    max_steps: int = 12,
    timeout: int = 300,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    job_id = f"os_multifile_{stamp}"
    job = {
        "id": job_id,
        "note": f"operator multifile: {objective[:80]}",
        "class": "fast",
        "continue_on_fail": True,
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-c",
                    (
                        "from core.pipeline import Pipeline; "
                        f"r=Pipeline().run({objective!r}); "
                        "print('status', getattr(r,'status',None), 'score', getattr(r,'verification_score',None))"
                    ),
                ],
                "timeout": timeout,
            }
        ],
    }
    return enqueue_job(job)


def speech_to_chat(text: str, *, job_id: Optional[str] = None) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "error": "empty transcription"}
    result = chat_post(f"[speech] {cleaned}", job_id=job_id, orchestrate=True)
    return {"ok": True, "turn": result}


def mcp_list() -> Dict[str, Any]:
    return {
        "updated": _now(),
        "local_tools": tools_list(),
        "gems": _list_gems(),
        "note": "MCP remote connectors are host-side; this lists local durable tools + gems.",
    }


def _list_gems() -> List[str]:
    gems_dir = ROOT / "gems"
    if not gems_dir.exists():
        return []
    return sorted(
        p.name for p in gems_dir.iterdir() if p.is_dir() and not p.name.startswith("_")
    )


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
