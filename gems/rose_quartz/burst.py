"""Cloud burst client — OpenAI-compatible (Grok / frontier) for hard fails only."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "memory" / "burst" / "ledger.jsonl"
STATE = ROOT / "memory" / "burst" / "state.json"


def burst_enabled() -> bool:
    return os.getenv("ETHER_BURST", "0") == "1" and bool(os.getenv("ETHER_BURST_API_KEY") or os.getenv("XAI_API_KEY"))


def _budget_ok() -> bool:
    max_calls = int(os.getenv("ETHER_BURST_MAX_CALLS", "40"))
    STATE.parent.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    st = {"day": day, "calls": 0}
    if STATE.exists():
        try:
            st = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    if st.get("day") != day:
        st = {"day": day, "calls": 0}
    if int(st.get("calls") or 0) >= max_calls:
        return False
    st["calls"] = int(st.get("calls") or 0) + 1
    STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")
    return True


def should_burst(objective: str, attempt: int, last_fail: bool) -> bool:
    if not burst_enabled():
        return False
    o = (objective or "").lower()
    hard = any(k in o for k in ("refactor", "multi", "module", "class ", "package", "patch", "file"))
    if hard:
        return True
    if last_fail and attempt >= 1:
        return True
    return False


def chat(messages: List[Dict[str, str]], max_tokens: int = 2048) -> Dict[str, Any]:
    """Call OpenAI-compatible Chat Completions API."""
    if not _budget_ok():
        return {"ok": False, "error": "burst daily budget exhausted"}

    base = (os.getenv("ETHER_BURST_URL") or "https://api.x.ai/v1").rstrip("/")
    model = os.getenv("ETHER_BURST_MODEL") or "grok-3"
    key = os.getenv("ETHER_BURST_API_KEY") or os.getenv("XAI_API_KEY") or ""
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    t0 = datetime.now(timezone.utc)
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(f"{base}/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        rec = {
            "ts": t0.isoformat(),
            "model": model,
            "tokens": usage.get("total_tokens"),
            "ok": True,
        }
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return {"ok": True, "content": content, "model": model, "usage": usage}
    except Exception as e:
        rec = {"ts": t0.isoformat(), "model": model, "ok": False, "error": str(e)[:200]}
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return {"ok": False, "error": str(e)}
