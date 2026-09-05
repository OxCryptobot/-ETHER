"""Living loop — batch that runs gems on real fixtures.

Walk a plan, PEP8-review, audit, pytest (repo_oracle / ToolRuntime path),
persist a lesson. Merge/ledger/toy workspaces live here.
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

FIXTURES: Dict[str, Path] = {
    "merge": ROOT / "fixtures" / "repo_oracle_merge",
    "ledger": ROOT / "fixtures" / "repo_oracle_ledger",
    "toy": ROOT / "fixtures" / "repo_oracle_toy",
    "lru": ROOT / "fixtures" / "repo_oracle_lru",
    "topo": ROOT / "fixtures" / "repo_oracle_topo",
    "intervals": ROOT / "fixtures" / "repo_oracle_intervals",
    "wallet": ROOT / "fixtures" / "repo_oracle_wallet",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_tests(
    workspace: Optional[Path] = None,
    code: Optional[str] = None,
    timeout: int = 45,
) -> Dict[str, Any]:
    """Run pytest via repo_oracle (same path ToolRuntime._obs_tests uses)."""
    from core.repo_oracle import run_project_pytest

    if workspace is not None:
        result = run_project_pytest(workspace, timeout=timeout)
        result["via"] = "workspace"
        result["workspace"] = str(workspace)
        return result

    body = code if code is not None else DEFAULT_TEST
    with tempfile.TemporaryDirectory(prefix="ether_living_") as tmp:
        tdir = Path(tmp)
        (tdir / "test_living.py").write_text(body, encoding="utf-8")
        result = run_project_pytest(tdir, timeout=timeout)
        result["via"] = "temp"
        return result


def pep8_workspace(workspace: Path) -> Dict[str, Any]:
    from core.pep8_reviewer import review_paths

    report = review_paths([workspace])
    return {
        "ok": bool(report.ok),
        "tool": report.tool,
        "n_critical": report.n_critical,
        "n_warning": report.n_warning,
        "via": "pep8_reviewer",
        "workspace": str(workspace),
    }


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


def first_py(workspace: Path) -> str:
    for p in sorted(workspace.rglob("*.py")):
        if "test" in p.parts:
            continue
        return p.read_text(encoding="utf-8", errors="replace")[:4000]
    return DEFAULT_TEST


def run_fixture(name: str, *, timeout: int = 60) -> Dict[str, Any]:
    """Grade a named repo_oracle fixture: pep8 + pytest + audit + lesson."""
    if name not in FIXTURES:
        raise KeyError(f"unknown fixture {name}")
    ws = FIXTURES[name]
    if not ws.exists():
        return {"name": name, "ok": False, "error": "missing workspace", "workspace": str(ws)}
    pep8 = pep8_workspace(ws)
    tests = run_tests(workspace=ws, timeout=timeout)
    audit = audit_code(first_py(ws))
    lesson = save_lesson(
        f"fixture={name} pep8={pep8.get('ok')} tests={tests.get('ok')} audit={audit.get('approved')}",
        kind=f"fixture:{name}",
    )
    return {
        "name": name,
        "workspace": str(ws),
        "pep8": pep8,
        "tests": {"ok": tests.get("ok"), "via": tests.get("via"), "score": tests.get("score")},
        "audit": audit,
        "lesson": str(lesson),
        "ok": True,  # graded without crashing
        "tests_ok": bool(tests.get("ok")),
        "pep8_ok": bool(pep8.get("ok")),
    }


def run_hard_pack(*, timeout: int = 60) -> Dict[str, Any]:
    """Batch: toy (easy) + merge + ledger (living pair)."""
    names = ("toy", "merge", "ledger")
    rows = [run_fixture(n, timeout=timeout) for n in names]
    save_lesson("hard_pack " + ",".join(f"{r['name']}:{r['tests_ok']}" for r in rows), kind="hard_pack")
    return {
        "ok": all(r.get("ok") for r in rows),
        "rows": rows,
        "toy_green": next(r["tests_ok"] for r in rows if r["name"] == "toy"),
        "n": len(rows),
    }


def run_pack_plus(*, timeout: int = 60) -> Dict[str, Any]:
    """4B product pack: living pair plus lru/topo/intervals when present."""
    names = ("toy", "merge", "ledger", "lru", "topo", "intervals")
    rows = []
    for name in names:
        if name not in FIXTURES or not FIXTURES[name].exists():
            rows.append({"name": name, "ok": False, "error": "missing", "tests_ok": False})
            continue
        rows.append(run_fixture(name, timeout=timeout))
    save_lesson("pack_plus " + ",".join(f"{r['name']}:{r.get('tests_ok')}" for r in rows), kind="pack_plus")
    return {"ok": all(r.get("ok") for r in rows), "rows": rows, "n": len(rows)}


def fabricate_stub(name: str, purpose: str = "") -> Dict[str, Any]:
    """Template fabricate only. Never claims LLM-authored tools."""
    from gems.grandidierite.fabricate import fabricate

    return fabricate(
        {
            "name": name,
            "docstring": purpose or f"stub {name}",
            "stub_only": True,
        }
    )


def run_living(plan: ExecutionPlan, *, code: str = DEFAULT_TEST) -> Dict[str, Any]:
    """Full batch: fix-task DAG first, then audit → pytest → flywheel lesson."""
    from core.loop.fix_dag import walk_fix
    from core.loop.flywheel import lesson_from_trace, prepend_lessons
    from core.loop.goal import classify_objective
    from core.loop.plan_exec import dispatch_walked
    from core.loop.plan_walk import walk_plan

    classified = classify_objective(plan.reasoning or "fix")
    _ = prepend_lessons(plan.reasoning or "fix")
    walked = walk_fix(plan.reasoning or "fix") if classified.get("uses_fix_dag") else walk_fix("fix")
    if plan.steps:
        walked = dispatch_walked(walk_plan(plan))
    audit = audit_code(code)
    tests = run_tests(code=code)
    lesson = save_lesson(
        f"living audit={audit.get('approved')} tests={tests.get('ok')} steps={len(walked)}"
    )
    fly = lesson_from_trace(
        {"tools": [r.get("tool") for r in walked if r.get("tool")], "ok": tests.get("ok")}
    )
    return {
        "ok": bool(tests.get("ok")) and bool(audit.get("ok")),
        "steps": walked,
        "audit": audit,
        "tests": {"ok": tests.get("ok"), "via": tests.get("via"), "score": tests.get("score")},
        "lesson": str(lesson),
        "flywheel": fly.get("text"),
        "n_steps": len(walked),
    }
