"""Exe-owned autonomy. Grok is optional. Honest PASS rules stay."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\Users\Otcde\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[2]

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def decide(*, ollama: bool, pending_live: int, last_ok: bool | None, writer_nt: bool) -> Dict[str, Any]:
    actions: List[str] = []
    if writer_nt:
        actions.append("pulse")
        actions.append("drain_live")
    else:
        actions.append("observe_only")
    if ollama and writer_nt:
        actions.append("4b_is_operator")
    else:
        actions.append("wait_ollama")
    if last_ok is False and writer_nt:
        actions.append("critique_then_one_hyp")
    if pending_live and not writer_nt:
        actions.append("live_stays_pending")
    return {
        "grok_required": False,
        "honest_gate": True,
        "soft_launch": False,
        "ollama": ollama,
        "actions": actions,
        "ts": _now(),
    }

def tick() -> Dict[str, Any]:
    root = _root()
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    ollama = False
    try:
        from scripts.live_host import ollama_up
        ollama = bool(ollama_up())
    except Exception:
        ollama = False
    pending = art / "jobs" / "pending"
    live_n = 0
    if pending.is_dir():
        for p in pending.glob("*.json"):
            try:
                row = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(row.get("class") or "").lower() == "live":
                live_n += 1
    last_ok = None
    last = art / "host_agent_last_job.json"
    if last.is_file():
        try:
            last_ok = bool(json.loads(last.read_text(encoding="utf-8")).get("ok"))
        except Exception:
            last_ok = None
    row = decide(ollama=ollama, pending_live=live_n, last_ok=last_ok, writer_nt=os.name == "nt")
    if os.name == "nt":
        try:
            from scripts.exe_pulse import pulse
            row["pulse"] = pulse(push=True)
        except Exception as exc:
            row["pulse_error"] = type(exc).__name__
        try:
            from scripts.drain_live_fifo import drain
            row["live"] = drain()
        except Exception as exc:
            row["live_error"] = type(exc).__name__
    (art / "autonomy_tick.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row
