"""Batch 9 item 9: pillar wiring on the real-goal path, behind default-off flags. No extra model calls.

ETHER_GEM_PREGATE=1 puts the Black Tourmaline gem (security) between apply_edit and the gate: an edit that
ADDS a shell, a dynamic import, eval/exec, a socket or a recursive delete to the goal file (count after the
edit > count before) is restored and fed back without spending a gate run. It can only reject edits, never
keep one, so it cannot make the gate less strict; it is off by default because a rejection changes which
replies reach the gate and therefore the 0/1 rewards the bandit learns from.

Not wired here (owner decision / not safe without design): swarm, MCP, LSP, multi-model routing.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict

from core.agent import gems

DANGER = {
    "subprocess": re.compile(r"\bsubprocess\b"),
    "os.system": re.compile(r"\bos\.(system|popen|exec\w*|spawn\w*)\s*\("),
    "__import__": re.compile(r"\b__import__\s*\("),
    "eval/exec": re.compile(r"(?<![\w.])(eval|exec)\s*\("),
    "socket": re.compile(r"\bsocket\b"),
    "rmtree": re.compile(r"\bshutil\.rmtree\s*\("),
    "importlib": re.compile(r"\bimportlib\.import_module\s*\("),
}


def pregate_on() -> bool:
    return os.environ.get("ETHER_GEM_PREGATE", "0").strip().lower() in ("1", "true", "on", "yes")


def _counts(text: str) -> Dict[str, int]:
    return {k: len(rx.findall(text or "")) for k, rx in DANGER.items()}


def pregate(original: str, after: str) -> Dict[str, Any]:
    """{"ok", "gem", "added": [pattern names whose count went up]}. Pure; reads nothing, calls no model."""
    row = gems.route_stage("security")
    before, now = _counts(original), _counts(after)
    added = sorted(k for k in DANGER if now[k] > before[k])
    return {"ok": not added, "gem": row.get("gem") or "black_tourmaline", "added": added}
