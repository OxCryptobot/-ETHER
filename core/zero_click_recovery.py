"""Moonshot 23 — Zero-click recovery on tool_runtime_failed_terminal.

Enqueue one scripted twin, then stop. Rate-limited.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
PENDING = ROOT / "artifacts" / "jobs" / "pending"


def maybe_recover(envelope: Dict[str, Any]) -> Optional[str]:
    if envelope.get("ok"):
        return None
    ft = str(envelope.get("failure_type") or "").lower()
    note = str(envelope.get("note") or "").lower()
    hay = ft + " " + note
    if "tool_runtime_failed_terminal" not in hay and "tool_runtime" not in hay:
        if ft not in ("timeout", "step_fail"):
            return None
        # only for toolish jobs
        if "tool_runtime" not in note and "tool" not in note:
            return None

    try:
        from core.playbook_limiter import allow_playbook, mark_playbook

        if not allow_playbook("tool_runtime_failed_terminal", "zero_click"):
            return None
    except Exception:
        pass

    try:
        from core.queue_governor import may_enqueue

        if not may_enqueue():
            return None
    except Exception:
        pass

    PENDING.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    jid = f"zcr_tool_runtime_scripted_{stamp}"
    job = {
        "id": jid,
        "class": "recovery",
        "source": "zero_click_recovery",
        "created": datetime.now(timezone.utc).isoformat(),
        "note": f"zero-click: scripted twin after {envelope.get('job_id')} tool_runtime fail",
        "continue_on_fail": True,
        "steps": [
            {
                "argv": [
                    ".venv/Scripts/python.exe",
                    "-m",
                    "pytest",
                    "tests/test_tool_runtime.py",
                    "tests/test_ast_transaction.py",
                    "-q",
                    "--tb=line",
                ],
                "timeout": 180,
            }
        ],
    }
    (PENDING / f"{jid}.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
    try:
        from core.playbook_limiter import mark_playbook

        mark_playbook("tool_runtime_failed_terminal", "zero_click")
    except Exception:
        pass
    return jid
