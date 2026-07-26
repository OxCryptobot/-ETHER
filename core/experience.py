"""Experience vault — store and retrieve PASS/FAIL trajectories for few-shot intelligence."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
VAULT_DIR = ROOT / "memory" / "experience"
PASS_PATH = VAULT_DIR / "pass.jsonl"
FAIL_PATH = VAULT_DIR / "fail.jsonl"


def experience_enabled() -> bool:
    return os.getenv("ETHER_EXPERIENCE", "1") == "1"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", (text or "").lower()))


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / max(1, len(ta | tb))


def record(
    *,
    objective: str,
    code: str,
    success: bool,
    confidence: float = 0.0,
    strategy: str = "",
    stderr: str = "",
    fail_kind: str = "",
    task_id: str = "",
) -> None:
    if not experience_enabled():
        return
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "objective": (objective or "")[:500],
        "code": (code or "")[:4000],
        "success": success,
        "confidence": confidence,
        "strategy": strategy,
        "stderr": (stderr or "")[:800],
        "fail_kind": fail_kind,
        "task_id": task_id,
    }
    path = PASS_PATH if success else FAIL_PATH
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _read_jsonl(path: Path, limit: int = 400) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        for line in lines:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return rows


def retrieve(objective: str, k: int = 3) -> Dict[str, Any]:
    """Return few-shot block from similar PASS examples + fail hints."""
    if not experience_enabled():
        return {"block": "", "n_pass": 0, "n_fail": 0}

    passes = _read_jsonl(PASS_PATH)
    fails = _read_jsonl(FAIL_PATH)

    scored_p = sorted(
        (( _overlap(objective, r.get("objective", "")), r) for r in passes),
        key=lambda x: x[0],
        reverse=True,
    )
    scored_f = sorted(
        (( _overlap(objective, r.get("objective", "")), r) for r in fails),
        key=lambda x: x[0],
        reverse=True,
    )

    top_p = [r for s, r in scored_p[:k] if s > 0.05]
    top_f = [r for s, r in scored_f[:2] if s > 0.05]

    parts: List[str] = []
    for i, r in enumerate(top_p, 1):
        parts.append(
            f"### Success example {i}\n"
            f"Objective: {r.get('objective','')}\n"
            f"Code:\n{r.get('code','')}\n"
        )
    for i, r in enumerate(top_f, 1):
        parts.append(
            f"### Related failure {i} (avoid)\n"
            f"Objective: {r.get('objective','')}\n"
            f"Fail kind: {r.get('fail_kind') or 'runtime'}\n"
            f"Stderr: {(r.get('stderr') or '')[:200]}\n"
        )

    block = "\n".join(parts)[:3500]
    return {"block": block, "n_pass": len(top_p), "n_fail": len(top_f)}
