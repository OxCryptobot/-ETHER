"""Collect live system state for the dashboard."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> Optional[Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except Exception:
        return ""


def _tail_jsonl(path: Path, limit: int = 40) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return list(reversed(rows))


def collect_snapshot() -> Dict[str, Any]:
    flywheel_dir = ROOT / "memory" / "flywheel"
    runs_dir = ROOT / "memory" / "runs"
    latest = _read_json(flywheel_dir / "latest.json") or {}
    last_fail = _read_json(flywheel_dir / "last_fail.json")
    history = _tail_jsonl(flywheel_dir / "history.jsonl", 50)
    heartbeat = _read_text(flywheel_dir / "heartbeat.txt").strip()

    runs: List[Dict[str, Any]] = []
    if runs_dir.exists():
        files = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
        for f in files:
            data = _read_json(f)
            if isinstance(data, dict):
                runs.append(
                    {
                        "id": data.get("task_id") or f.stem,
                        "objective": (data.get("objective") or "")[:120],
                        "status": data.get("status"),
                        "confidence": data.get("confidence"),
                        "started_at": data.get("started_at"),
                        "finished_at": data.get("finished_at"),
                        "retries": data.get("retries", 0),
                        "stages": [
                            {
                                "stage": s.get("stage"),
                                "success": s.get("success"),
                                "detail": (s.get("detail") or "")[:80],
                                "duration_ms": s.get("duration_ms"),
                            }
                            for s in (data.get("stages") or [])
                        ],
                    }
                )

    gems = [
        "clear-quartz",
        "rose-quartz",
        "citrine",
        "selenite",
        "amethyst",
        "black-tourmaline",
        "labradorite",
        "grandidierite",
    ]

    # pass rate from history
    if history:
        passes = sum(1 for h in history if h.get("ok"))
        pass_rate = round(passes / len(history), 3)
    else:
        pass_rate = None

    connections = {
        "docker": shutil.which("docker") is not None,
        "ollama": shutil.which("ollama") is not None,
        "qdrant_url": os.getenv("QDRANT_URL", "http://localhost:6333"),
        "ollama_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "primary_model": os.getenv("ETHER_PRIMARY_MODEL", ""),
        "embed_model": os.getenv("ETHER_EMBED_MODEL", "nomic-embed-text"),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": "@ETHER",
        "version": "0.1.1",
        "heartbeat": heartbeat or None,
        "flywheel": {
            "latest": latest,
            "last_fail": last_fail,
            "history": history,
            "pass_rate": pass_rate,
            "cycles": len(history),
        },
        "runs": runs,
        "gems": {"registered": gems, "count": len(gems)},
        "workspace": {
            "root": str(ROOT),
            "status_md": (_read_text(ROOT / "STATUS.md")[:2000]),
            "flywheel_md": (_read_text(ROOT / "FLYWHEEL.md")[:1500]),
        },
        "connections": connections,
        "policy": {
            "min_confidence": float(os.getenv("ETHER_FLYWHEEL_MIN_CONFIDENCE", "0.7")),
            "max_retries": int(os.getenv("ETHER_FLYWHEEL_MAX_RETRIES", "3")),
            "interval": int(os.getenv("ETHER_FLYWHEEL_INTERVAL", "900")),
            "push": os.getenv("ETHER_FLYWHEEL_PUSH", "0") == "1",
            "sandbox_retry": os.getenv("ETHER_SANDBOX_RETRY", "1") == "1",
            "use_context": os.getenv("ETHER_USE_CONTEXT", "1") == "1",
        },
        "matrix": _build_matrix(latest, history, runs),
    }


def _build_matrix(
    latest: Dict[str, Any],
    history: List[Dict[str, Any]],
    runs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compact operational matrix for the UI."""
    gates = (latest or {}).get("gates") or {}
    steps = (latest or {}).get("steps") or {}
    return {
        "quality_pass": (latest or {}).get("ok"),
        "confidence": gates.get("confidence"),
        "audit": gates.get("audit_approved"),
        "static": gates.get("static_ok"),
        "agentic": gates.get("agentic_ok"),
        "reason": gates.get("agentic_reason"),
        "steps": [
            {"name": k, "ok": v.get("ok"), "ms": int((v.get("duration_s") or 0) * 1000)}
            for k, v in steps.items()
        ],
        "recent_pass_fail": [
            {"ts": h.get("timestamp"), "ok": h.get("ok"), "conf": (h.get("gates") or {}).get("confidence")}
            for h in history[:20]
        ],
        "active_runs": sum(1 for r in runs if r.get("status") == "complete"),
        "error_runs": sum(1 for r in runs if r.get("status") == "error"),
    }
