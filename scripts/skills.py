"""Six skills the worker can run without the 1650. None of them write app_alive."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
REVIEW = (
    "scripts/host_main.py",
    "scripts/runner_register.py",
    "scripts/ether_evolve.py",
    "scripts/self_heal.py",
    "scripts/origin_publish.py",
    "scripts/skills.py",
)


def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    return ROOT


def batchphase() -> Dict[str, Any]:
    pending = _root() / "artifacts" / "jobs" / "pending"
    fast = live = 0
    if pending.is_dir():
        from scripts.drain_fast_fifo import is_fast
        for path in pending.glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if is_fast(job):
                fast += 1
            else:
                live += 1
    return {"ok": True, "fast_pending": fast, "live_pending": live, "ran": False}


def goal_skill(walk: Dict[str, Any] | None = None) -> Dict[str, Any]:
    from scripts.ether_evolve import _goal
    return _goal(walk or {"weak": []})


def host_agent_live() -> Dict[str, Any]:
    from scripts.live_status import write
    from scripts.runner_register import _count
    status = write()
    runners = _count()
    return {
        "ok": (not status.get("stale")) and runners not in (0, None),
        "stale": bool(status.get("stale")),
        "runners": runners,
        "app_alive_ts": status.get("app_alive_ts"),
        "note": "observe_only" if os.name != "nt" else "1650",
    }


def keep_pushing() -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": True, "pushed": False, "note": "observe_only"}
    return {"ok": True, "pushed": False, "note": "exe_publish_on_tick"}


def pep8_review() -> Dict[str, Any]:
    bad: List[str] = []
    root = _root()
    for rel in REVIEW:
        path = root / rel
        if not path.is_file():
            bad.append(rel + ":missing")
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            bad.append(f"{rel}:{exc.lineno}")
    return {"ok": not bad, "errors": bad}


def super_auditor(parts: Dict[str, Any]) -> Dict[str, Any]:
    gaps: List[str] = []
    host = parts.get("host-agent-live") or {}
    if host.get("stale"):
        gaps.append("app_alive_stale")
    if host.get("runners") == 0:
        gaps.append("no_github_runner")
    if not (parts.get("pep8-python-reviewer") or {}).get("ok", True):
        gaps.append("syntax")
    return {"ok": not gaps, "gaps": gaps}


def run_skills(walk: Dict[str, Any] | None = None) -> Dict[str, Any]:
    parts = {
        "batchphase": batchphase(),
        "goal": goal_skill(walk),
        "host-agent-live": host_agent_live(),
        "keep-pushing": keep_pushing(),
        "pep8-python-reviewer": pep8_review(),
    }
    parts["super-auditor"] = super_auditor(parts)
    return parts
