"""Lightweight style gate for strangler pure modules.

Does not require ruff installed. Checks importability + basic AST parse.
Optional ruff when ETHER_RUFF_GATE=1 and ruff available.
"""
from __future__ import annotations

import ast
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "strangler_style_gate.json"

TARGETS = [
    "core/pipeline_tool_first.py",
    "core/pipeline_score.py",
    "core/pipeline_terminal.py",
    "core/pipeline_adapter.py",
    "core/pipeline_burst.py",
    "core/pipeline_select.py",
    "core/pipeline_strangler.py",
]


def check() -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    ok_n = 0
    for rel in TARGETS:
        path = ROOT / rel
        entry: Dict[str, Any] = {"path": rel}
        if not path.exists():
            entry["ok"] = False
            entry["error"] = "missing"
            results.append(entry)
            continue
        try:
            src = path.read_text(encoding="utf-8")
            ast.parse(src)
            entry["ok"] = True
            entry["lines"] = src.count("\n") + 1
            ok_n += 1
        except SyntaxError as e:
            entry["ok"] = False
            entry["error"] = f"SyntaxError:{e}"
        results.append(entry)

    ruff_info: Dict[str, Any] = {"ran": False}
    if (os.getenv("ETHER_RUFF_GATE") or "").strip() == "1":
        try:
            from core.ruff_gate import run_ruff

            paths = [ROOT / t for t in TARGETS if (ROOT / t).exists()]
            ruff_info = run_ruff(paths, cwd=ROOT)
            ruff_info["ran"] = True
        except Exception as e:
            ruff_info = {"ran": True, "ok": False, "error": str(e)[:160]}

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "ok": ok_n == len(TARGETS),
        "ok_n": ok_n,
        "n": len(TARGETS),
        "results": results,
        "ruff": ruff_info,
        "note": "AST parse hygiene on strangler slices; ruff optional",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
