"""Drain LIVE FIFO on the 1650 exe only. Ubuntu must skip."""
from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
PENDING = ROOT / "artifacts" / "jobs" / "pending"
DONE = ROOT / "artifacts" / "jobs" / "done"
FAILED = ROOT / "artifacts" / "jobs" / "failed"

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _normalize_step(step: Any) -> Dict[str, Any]:
    if isinstance(step, dict):
        return step
    if isinstance(step, list):
        return {"argv": [str(x) for x in step]}
    if isinstance(step, str) and step.strip():
        return {"argv": [step]}
    return {}

def is_live(job: Dict[str, Any]) -> bool:
    return str(job.get("class") or "").lower() == "live"

def writer_ok() -> bool:
    if os.name == "nt":
        return True
    attach = ROOT / "artifacts" / "host_attach.json"
    if not attach.is_file():
        return False
    try:
        row = json.loads(attach.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(row.get("ollama")) and str(row.get("writer") or "") == "exe"

def run_job(path: Path) -> Dict[str, Any]:
    job = json.loads(path.read_text(encoding="utf-8"))
    jid = str(job.get("id") or path.stem)
    if not is_live(job):
        return {"id": jid, "skipped": True, "ok": True, "note": "FAST stays on matrix-worker"}
    if not writer_ok():
        return {"id": jid, "skipped": True, "ok": True, "note": "LIVE waits for 1650 exe"}
    ok = True
    tails: List[str] = []
    for raw in job.get("steps") or []:
        step = _normalize_step(raw)
        argv = list(step.get("argv") or [])
        if argv and argv[0].replace("\\", "/").endswith("python.exe"):
            argv[0] = sys.executable
        if not argv:
            continue
        try:
            proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=int(step.get("timeout") or 180))
            tails.append((proc.stdout or "")[-300:] + (proc.stderr or "")[-200:])
            if proc.returncode != 0:
                ok = False
        except Exception as exc:
            ok = False
            tails.append(type(exc).__name__)
    report = {"job_id": jid, "ok": ok, "rc": 0 if ok else 1, "finished": _now(), "class": "live", "tail": "\n".join(tails)[-800:]}
    dest = DONE if ok else FAILED
    dest.mkdir(parents=True, exist_ok=True)
    (dest / path.name).write_text(json.dumps({**job, "report": report}, indent=2) + "\n", encoding="utf-8")
    path.unlink(missing_ok=True)
    return report

def drain() -> Dict[str, Any]:
    PENDING.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in PENDING.glob("*.json") if p.name != ".gitkeep")
    reports = [run_job(p) for p in files]
    return {"ok": all(r.get("ok") or r.get("skipped") for r in reports), "n": len(reports), "jobs": reports}

if __name__ == "__main__":
    print(json.dumps(drain(), indent=2))
