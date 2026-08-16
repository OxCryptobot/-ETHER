"""Pipeline god-file strangler status.

Tracks extracted pure modules vs core/pipeline.py size.
Does NOT modify Pipeline.run. Measurement + inventory only.
Default path stays identical — THE LAW.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "pipeline_strangler.json"
PIPELINE = ROOT / "core" / "pipeline.py"

EXTRACTED: List[Dict[str, str]] = [
    {"mod": "core.pipeline_tool_first", "role": "tool-first terminal decision"},
    {"mod": "core.pipeline_select", "role": "strategy selection + bandit context"},
    {"mod": "core.pipeline_hooks", "role": "bandit context / hooks"},
    {"mod": "core.pipeline_burst", "role": "burst-on-retry policy slice"},
    {"mod": "core.pipeline_score", "role": "score clamp + degrade merge + envelopes"},
    {"mod": "core.loop.tool_first", "role": "pure tool-first terminal helper"},
]

WARN_BYTES = 40_000


def _import_ok(mod: str) -> Dict[str, Any]:
    try:
        __import__(mod)
        return {"mod": mod, "ok": True}
    except Exception as e:
        return {"mod": mod, "ok": False, "error": f"{type(e).__name__}:{e}"[:160]}


def compute() -> Dict[str, Any]:
    size = PIPELINE.stat().st_size if PIPELINE.exists() else 0
    lines = 0
    if PIPELINE.exists():
        try:
            lines = PIPELINE.read_text(encoding="utf-8", errors="replace").count("\n") + 1
        except Exception:
            lines = 0

    imports = [_import_ok(e["mod"]) for e in EXTRACTED]
    ok_n = sum(1 for i in imports if i.get("ok"))

    tool_first_ok = False
    try:
        from core.pipeline_tool_first import decide_pipeline_tool_first

        d = decide_pipeline_tool_first(
            tool_runtime_enabled=True, tool_runtime_done=False
        )
        tool_first_ok = d.should_fail is True and d.degrade_marker == (
            "tool_runtime_failed_terminal"
        )
    except Exception:
        tool_first_ok = False

    score_ok = False
    try:
        from core.pipeline_score import clamp_score, merge_degraded, terminal_fail_envelope

        score_ok = (
            clamp_score(1.5) == 1.0
            and clamp_score(-1) == 0.0
            and merge_degraded(["a"], "a", "b") == ["a", "b"]
            and terminal_fail_envelope(stage="t", marker="m")["ok"] is False
        )
    except Exception:
        score_ok = False

    status = "IN_PROGRESS"
    if size == 0:
        status = "MISSING"
    elif size <= WARN_BYTES and ok_n == len(EXTRACTED) and tool_first_ok and score_ok:
        status = "HEALTHY_SLICE"
    elif ok_n == len(EXTRACTED) and tool_first_ok and score_ok:
        status = "STRANGLER_ACTIVE"

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "pipeline_bytes": size,
        "pipeline_lines": lines,
        "warn_bytes": WARN_BYTES,
        "over_budget": size > WARN_BYTES,
        "extracted_n": len(EXTRACTED),
        "extracted_ok": ok_n,
        "imports": imports,
        "tool_first_contract_ok": tool_first_ok,
        "score_contract_ok": score_ok,
        "status": status,
        "note": (
            "God-file still large; pure slices must stay importable. "
            "No Pipeline.run body change in this phase."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
