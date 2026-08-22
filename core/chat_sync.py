"""Immediate chat bus sync — dashboard runs on the host, so push NOW.

Latency doctrine:
  Do not wait for host_agent liveness (55s) or chat dirty interval (12s).
  After escalate / clear / reply, dashboard calls push_chat_now() in a
  background thread so the HTTP response returns instantly.

Training wheels ON. Force-add only artifacts/chat paths.
"""
from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()

_lock = threading.Lock()
_last_push_ts = 0.0
_MIN_GAP_S = 1.5  # avoid stampede; still near-instant


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(argv: List[str], timeout: int = 45) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _paths() -> List[str]:
    try:
        from core.chat_bridge import chat_paths_for_push

        return chat_paths_for_push()
    except Exception:
        paths: List[str] = []
        chat = ROOT / "artifacts" / "chat"
        if chat.exists():
            for sub in ("inbox", "outbox", "turns", "archive"):
                if (chat / sub).exists():
                    paths.append(f"artifacts/chat/{sub}")
            if (chat / "pending_grok.json").exists():
                paths.append("artifacts/chat/pending_grok.json")
        if (ROOT / "artifacts" / "chat_turn_latest.json").exists():
            paths.append("artifacts/chat_turn_latest.json")
        return paths


def push_chat_now(*, message: str = "chat bus: immediate sync") -> Dict[str, Any]:
    """Blocking push of chat artifacts. Prefer push_chat_async from API handlers."""
    global _last_push_ts
    import time

    with _lock:
        now = time.time()
        if now - _last_push_ts < _MIN_GAP_S:
            return {"ok": True, "skipped": "throttle", "updated": _now()}
        paths = _paths()
        if not paths:
            return {"ok": True, "skipped": "empty", "updated": _now()}
        try:
            _run(["git", "add", "-f", "--"] + paths, timeout=30)
            c = _run(["git", "commit", "-m", message], timeout=25)
            combined = ((c.stdout or "") + (c.stderr or "")).lower()
            if c.returncode != 0 and "nothing to commit" in combined:
                _last_push_ts = now
                try:
                    from core.chat_bridge import clear_dirty

                    clear_dirty()
                except Exception:
                    pass
                return {"ok": True, "skipped": "nothing_to_commit", "updated": _now()}
            if c.returncode != 0:
                return {
                    "ok": False,
                    "error": (c.stderr or c.stdout or "commit failed")[:300],
                    "updated": _now(),
                }
            p = _run(["git", "push", "origin", "main"], timeout=60)
            if p.returncode != 0:
                _run(["git", "fetch", "origin"], timeout=90)
                _run(["git", "pull", "--rebase", "origin", "main"], timeout=60)
                _run(["git", "add", "-f", "--"] + paths, timeout=30)
                _run(["git", "commit", "-m", message], timeout=25)
                p = _run(["git", "push", "origin", "main"], timeout=60)
            _last_push_ts = time.time()
            if p.returncode == 0:
                try:
                    from core.chat_bridge import clear_dirty

                    clear_dirty()
                except Exception:
                    pass
                return {"ok": True, "paths": len(paths), "updated": _now()}
            return {
                "ok": False,
                "error": ((p.stderr or "") + (p.stdout or ""))[:300],
                "updated": _now(),
            }
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "updated": _now()}


def push_chat_async(*, message: str = "chat bus: immediate sync") -> None:
    """Fire-and-forget so API latency stays low."""

    def _run_push() -> None:
        try:
            push_chat_now(message=message)
        except Exception:
            pass

    t = threading.Thread(target=_run_push, name="ether-chat-sync", daemon=True)
    t.start()
