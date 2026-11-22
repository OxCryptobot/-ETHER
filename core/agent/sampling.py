"""Batch 8: sampling temperature by try index (ETHER_SAMPLE_TEMP) + duplicate-reply accounting.

Why: every real-goal reply is greedy (scripts/host_main.py `_code` -> scripts/live_edit_tx.py `_ask`,
temperature=0). A goal gets up to MAX_TRIES=3 attempts (goal_source.py), and with the same arm a greedy
retry tends to return the same reply = the same miss. A fresh sample on a retry is the cheapest
repeated-sampling lever (docs/RL_METHODS.md, rl_sim E3).

Flags (all default off; with them unset prompts, model calls and decisions are unchanged):
  ETHER_SAMPLE_TEMP   comma list indexed by try number on this goal (prior attempts + inner retry),
                      the last value repeats. "0,0.7" = greedy first attempt, T=0.7 after. Unset/"0" = off.
  ETHER_DEDUP_REPLY=1 a reply whose edit is byte-identical to one the gate already reverted for this
                      goal, on the same target-file content, is not re-gated; it is logged as the same
                      miss (reward 0, note "duplicate reply"). The verdict reused is the gate's own.
Always on (measurement only, no decision changes): each graded attempt's trajectory row gets
`reply_hash` (12 hex of the extracted edit), `file_hash`, `temp`, and `dup` (same goal + same edit
hash seen before) so first_hour_report can show the duplicate-reply rate in Phase 0.
"""
from __future__ import annotations

import hashlib
import inspect
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

MAX_TEMP = 1.2


def schedule() -> List[float]:
    raw = (os.getenv("ETHER_SAMPLE_TEMP") or "").strip()
    if not raw or raw == "0":
        return []
    out: List[float] = []
    for part in raw.split(","):
        try:
            out.append(min(MAX_TEMP, max(0.0, float(part))))
        except ValueError:
            return []
    return out if any(t > 0 for t in out) else []


def enabled() -> bool:
    return bool(schedule())


def temp_for(index: int) -> float:
    s = schedule()
    if not s:
        return 0.0
    return s[min(max(0, int(index)), len(s) - 1)]


def dedup_on() -> bool:
    return os.getenv("ETHER_DEDUP_REPLY", "0") == "1"


def accepts_temperature(fn: Callable[..., Any]) -> bool:
    flag = getattr(fn, "accepts_temperature", None)
    if flag is not None:
        return bool(flag)
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "temperature" or p.kind == p.VAR_KEYWORD for p in params)


def with_temp(ask: Callable[..., str], temp: float) -> Callable[..., str]:
    """ask unchanged at T=0 or when it cannot take a temperature; else a wrapper passing it."""
    if temp <= 0.0 or not accepts_temperature(ask):
        return ask

    def sampled(prompt: str, n: int = 240) -> str:
        return ask(prompt, n=n, temperature=temp)

    return sampled


def edit_hash(edit: Dict[str, Any]) -> str:
    parts = [str(edit.get("function") or "").strip(), str(edit.get("span") or "").strip()]
    for k, v in sorted((edit.get("assigns") or {}).items()):
        parts.append(f"{k}={str(v).strip()}")
    blob = "\n\x00".join(parts)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12] if blob.strip("\n\x00") else ""


def file_hash(text: str, baseline: Optional[Dict[str, str]] = None) -> str:
    """Target-file content + the guard suite's baseline (a kept edit elsewhere changes it)."""
    blob = (text or "") + "\n\x00" + "\n".join(f"{k}={v}" for k, v in sorted((baseline or {}).items()))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def seen_before(rows: List[Dict[str, Any]], goal_id: str, h: str) -> bool:
    return bool(h) and any(r.get("goal") == goal_id and r.get("reply_hash") == h for r in rows)


def reverted_before(root: Path, goal_id: str, h: str, fh: str,
                    rows: Optional[List[Dict[str, Any]]] = None) -> bool:
    """The gate already refused this exact edit for this goal on this exact state (target file content
    + the guard suite's baseline statuses, both folded into `fh`)."""
    if not h or not fh:
        return False
    if rows is None:
        from core.agent.outcome import trajectories

        rows = trajectories(root)
    return any(r.get("goal") == goal_id and r.get("reply_hash") == h and r.get("file_hash") == fh
               and r.get("kind") == "fail" for r in rows)
