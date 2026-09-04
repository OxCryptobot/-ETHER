"""Living loop — one batch that actually runs gems.

Walk a plan, audit the artifact, run pytest (Clear Quartz / repo_oracle),
persist a lesson. This is the Phase-3/4 body, not a catalog.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.schemas import ExecutionPlan

ROOT = Path(__file__).resolve().parents[2]
LESSONS = ROOT / "artifacts" / "lessons.jsonl"

DEFAULT_TEST = "def test_living_ok():\n    assert 1 + 1 == 2\n"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_tests(
    workspace: Optional[Path] = None,
    code: Optional[str] = None,
    timeout: int = 45,
) -> Dict[str, Any]:
    """Run pytest via repo_oracle (same path ToolRuntime._obs_tests uses).

    If no workspace, write `code` (or DEFAULT_TEST) into a temp dir and grade it.
    """
    from core.repo_oracle import run_project_pytest

    if workspace is not None:
        result = run_project_pytest(workspace, timeout=timeout)
        result["via"] = "workspace"
        return result

    body = code if code is not None else DEFAULT_TEST
    with tempfile.TemporaryDirectory(prefix="ether_living_") as tmp:
        tdir = Path(tmp)
        (tdir / "test_living.py").write_text(body, encoding="utf-8")
        result = run_project_pytest(tdir, timeout=timeout)
        result["via"] = "temp"
        return result


def audit_code(artifact: str) -> Dict[str, Any]:
    from core.schemas import Envelope, BlackTourmalineRequest
    from gems.black_tourmaline.security import BlackTourmaline

    gem = BlackTourmaline()
    env = Envelope(
        task_id=uuid4(),
        target_gem="black-tourmaline",
        payload=BlackTourmalineRequest(artifact=artifact, artifact_type="code"),
    )
    res = gem.execute(env)
    ok = res.error is None
    payload = res.payload
    approved = bool(getattr(payload, "approved", False)) if payload is not None else False
    return {
        "ok": ok and approved,
        "approved": approved,
        "error": None if res.error is None else str(res.error.message),
        "via": "black_tourmaline",
    }


def save_lesson(text: str, *, kind: str = "living") -> Path:
    LESSONS.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": _now(), "kind": kind, "text": (text or "")[:800]}
    with LESSONS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return LESSONS


def run_living(plan: ExecutionPlan, *, code: str = DEFAULT_TEST) -> Dict[str, Any]:
    """Full batch: walk → dispatch → audit → pytest → lesson."""
    from core.loop.plan_exec import dispatch_walked
    from core.loop.plan_walk import walk_plan

    walked = dispatch_walked(walk_plan(plan))
    audit = audit_code(code)
    tests = run_tests(code=code)
    lesson = save_lesson(
        f"living audit={audit.get('approved')} tests={tests.get('ok')} steps={len(walked)}"
    )
    return {
        "ok": bool(tests.get("ok")) and bool(audit.get("ok")),
        "steps": walked,
        "audit": audit,
        "tests": {"ok": tests.get("ok"), "via": tests.get("via"), "score": tests.get("score")},
        "lesson": str(lesson),
        "n_steps": len(walked),
    }
