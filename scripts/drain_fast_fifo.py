"""Drain FAST FIFO on Ubuntu. LIVE jobs stay pending for the 1650."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
LAST = ROOT / "artifacts" / "host_agent_last_job.json"
STATUS = ROOT / "artifacts" / "host_agent_status.json"

LIVE_MARKERS = ("ollama", "unaided", "qwen", "live_4b", "policy=model")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rewrite_argv(argv: List[str]) -> List[str]:
    out = list(argv)
    if out and out[0].replace("\\", "/").endswith("python.exe"):
        out[0] = sys.executable
    return out


def is_fast(job: Dict[str, Any]) -> bool:
    if str(job.get("class") or "").lower() == "live":
        return False
    blob = json.dumps(job).lower()
    if any(m in blob for m in LIVE_MARKERS) and "test_live_" not in blob:
        return False
    return True


def run_job(path: Path) -> Dict[str, Any]:
    job = json.loads(path.read_text(encoding="utf-8"))
    jid = str(job.get("id") or path.stem)
    if not is_fast(job):
        return {"id": jid, "ok": False, "skipped": True, "note": "LIVE stays on 1650"}
    ok = True
    tails: List[str] = []
    for step in job.get("steps") or []:
        argv = _rewrite_argv(list(step.get("argv") or []))
        if not argv:
            continue
        timeout = int(step.get("timeout") or 60)
        try:
            proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
            tails.append((proc.stdout or "")[-400:] + (proc.stderr or "")[-200:])
            if proc.returncode != 0:
                ok = False
        except Exception as exc:
            ok = False
            tails.append(type(exc).__name__)
    report = {
        "job_id": jid,
        "ok": ok,
        "rc": 0 if ok else 1,
        "finished": _now(),
        "note": "FAST drain on matrix-worker. Dual chat locked.",
        "class": "fast",
        "measurement": True,
        "tail": "\n".join(tails)[-800:],
    }
    DONE.mkdir(parents=True, exist_ok=True)
    (DONE / path.name).write_text(json.dumps({**job, "report": report}, indent=2) + "\n", encoding="utf-8")
    ops = jid.startswith("medic") or "health_check" in json.dumps(job)
    LAST.parent.mkdir(parents=True, exist_ok=True)
    if not ops:
        LAST.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    path.unlink(missing_ok=True)
    return report


def drain() -> Dict[str, Any]:
    PENDING.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in PENDING.glob("*.json") if p.name != ".gitkeep")
    reports = [run_job(p) for p in files]
    prev: Dict[str, Any] = {}
    if STATUS.is_file():
        try:
            prev = json.loads(STATUS.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    attach: Dict[str, Any] = {}
    ap = ROOT / "artifacts" / "host_attach.json"
    if ap.is_file():
        try:
            attach = json.loads(ap.read_text(encoding="utf-8"))
        except Exception:
            attach = {}
    ollama = attach.get("ollama")
    if ollama is None:
        ollama = prev.get("ollama")
    lane = attach.get("live_lane") or prev.get("live_lane")
    status = {
        "heartbeat": _now(),
        "phase": "idle" if not files else "draining",
        "current_job": None,
        "source": "matrix-worker",
        "pending_left": len([p for p in PENDING.glob("*.json") if p.name != ".gitkeep"]),
        "note": "FAST heartbeat. ollama/lane owned by 1650 attach.",
    }
    if ollama is not None:
        status["ollama"] = bool(ollama)
    if lane:
        status["live_lane"] = str(lane)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    return {"ok": all(r.get("ok") or r.get("skipped") for r in reports), "n": len(reports), "jobs": reports}


if __name__ == "__main__":
    print(json.dumps(drain(), indent=2))
