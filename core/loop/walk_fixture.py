"""Bounded fixture walk. Not Pipeline.run (that timed out). Not a gate count.

Applies parseable `# BUG: should …` replace_once steps on a temp copy, then pytest.
Unparsed BUG lines stay for 4B unaided. policy=craft_helper.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List


def walk_bounded(name: str, *, timeout: int = 45) -> Dict[str, Any]:
    from core.hard_live_playbook import mutations_from_workspace
    from core.loop.living import FIXTURES, run_tests

    src = FIXTURES[name]
    if not src.exists():
        return {"ok": False, "name": name, "error": "missing", "gate_count": False}
    tmp = Path(tempfile.mkdtemp(prefix=f"ether_walk_{name}_"))
    try:
        dest = tmp / src.name
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        steps = mutations_from_workspace(dest, limit=8)
        applied = _apply(dest, steps)
        tests = run_tests(workspace=dest, timeout=min(20, int(timeout)))
        return {
            "ok": True,
            "name": name,
            "policy": "craft_helper",
            "gate_count": False,
            "n_steps": len(steps),
            "n_applied": applied,
            "tests_ok": bool(tests.get("ok")),
            "workspace": str(dest),
            "note": "Bounded craft walk. Unparsed BUG lines need 4B unaided. Not Pipeline.run.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "name": name,
            "policy": "craft_helper",
            "gate_count": False,
            "error": f"{type(exc).__name__}:{exc}"[:200],
            "note": "Bounded craft walk failed closed. Not unaided LIVE.",
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _apply(root: Path, steps: List[Dict[str, Any]]) -> int:
    n = 0
    for step in steps:
        if str(step.get("tool") or "") != "replace_once":
            continue
        args = step.get("args") or {}
        rel = str(args.get("path") or "")
        old = args.get("old")
        new = args.get("new")
        if not rel or old is None or new is None:
            continue
        fp = root / rel
        if not fp.is_file():
            continue
        text = fp.read_text(encoding="utf-8")
        if old not in text:
            continue
        fp.write_text(text.replace(old, new, 1), encoding="utf-8")
        n += 1
    return n
