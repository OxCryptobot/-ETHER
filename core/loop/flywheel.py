"""Pytest-as-judge flywheel: lessons from tool traces, prepended to the next job."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
LESSONS = ROOT / "artifacts" / "lessons.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lesson_from_trace(scoreboard: Dict[str, Any]) -> Dict[str, Any]:
    from core.loop.traces import labradorite_from_trace

    lab = labradorite_from_trace(scoreboard)
    row = {
        "ts": _now(),
        "kind": "trace",
        "text": str(lab.get("critique") or "no trace")[:400],
        "tools": list(lab.get("tools") or []),
        "playbook": False,
        "needs_run_tests": bool(lab.get("needs_run_tests")),
    }
    LESSONS.parent.mkdir(parents=True, exist_ok=True)
    with LESSONS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def last_lessons(n: int = 7) -> List[Dict[str, Any]]:
    if not LESSONS.exists():
        return []
    lines = LESSONS.read_text(encoding="utf-8").splitlines()
    out: List[Dict[str, Any]] = []
    for line in lines[-max(1, n) :]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def prepend_lessons(prompt: str, n: int = 3) -> str:
    rows = last_lessons(n)
    if not rows:
        return prompt
    block = "Prior lessons:\n" + "\n".join(str(r.get("text") or "") for r in rows)
    return f"{block}\n\n{prompt}"


def daily_scoreboard(scoreboards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Last-N unaided tape. Numbers only."""
    n = len(scoreboards)
    ok = 0
    seconds: List[float] = []
    tests = 0
    for board in scoreboards:
        results = board.get("results") if isinstance(board, dict) else None
        row = results[0] if isinstance(results, list) and results else board
        if not isinstance(row, dict):
            continue
        if row.get("ok"):
            ok += 1
        try:
            seconds.append(float(row.get("seconds") or 0))
        except (TypeError, ValueError):
            pass
        tools = row.get("tools") or []
        if isinstance(tools, list) and "run_tests" in tools:
            tests += 1
    median = sorted(seconds)[len(seconds) // 2] if seconds else 0.0
    return {
        "n": n,
        "ok": ok,
        "run_tests": tests,
        "median_s": round(median, 1),
        "tape": f"{ok}/{n} unaided · run_tests {tests}/{n} · median {round(median, 1)}s",
    }
