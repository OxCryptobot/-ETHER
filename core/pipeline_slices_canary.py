"""Phase 2A — remaining strangler pure-slice canaries.

prep, context, oracle shape, tool_first. No Pipeline.run. Adapter OFF.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "pipeline_slices_canary.json"


def run_matrix() -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        cases.append({"name": name, "pass": bool(ok), "detail": detail[:120]})

    # prep
    try:
        from core.pipeline_prep import no_code_prep, prepare_code_for_sandbox

        with no_code_prep():
            code, meta = prepare_code_for_sandbox("x = 1\n", "simple")
        add("prep_bypass", code.strip().startswith("x") and meta.get("bypassed") is True, str(meta))
    except Exception as e:
        add("prep_bypass", False, str(e))

    # context
    try:
        from core.pipeline_context import bandit_context

        c = bandit_context("refactor module layout", tier=2, fail_kind="timeout")
        add(
            "context_multifile",
            c.get("multifile") is True and c.get("tier") == 2,
            str(c),
        )
        c2 = bandit_context("add one function", tier=0)
        add("context_simple", isinstance(c2.get("multifile"), bool), str(c2))
    except Exception as e:
        add("context_multifile", False, str(e))

    # tool_first
    try:
        from core.pipeline_tool_first import decide_pipeline_tool_first

        fail = decide_pipeline_tool_first(
            tool_runtime_enabled=True, tool_runtime_done=False
        )
        add(
            "tool_first_fail",
            fail.should_fail and fail.degrade_marker == "tool_runtime_failed_terminal",
            fail.reason,
        )
        ok = decide_pipeline_tool_first(
            tool_runtime_enabled=True, tool_runtime_done=True, score=1.0
        )
        add("tool_first_ok", ok.should_fail is False, ok.reason)
    except Exception as e:
        add("tool_first_fail", False, str(e))

    # oracle shape (no repo pytest required — disabled path)
    try:
        from core.pipeline_oracle import apply_repo_oracle_gate

        # When hook returns disabled/None shape, active False
        out = apply_repo_oracle_gate(
            "print(1)\n",
            "noop",
            execution_score=1.0,
            verification_score=1.0,
            confidence=1.0,
        )
        add(
            "oracle_callable",
            isinstance(out, dict) and "active" in out,
            str(out)[:80],
        )
    except Exception as e:
        add("oracle_callable", False, str(e))

    from core.pipeline_adapter import terminal_adapter_enabled

    passed = sum(1 for c in cases if c["pass"])
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "2A",
        "n": len(cases),
        "passed": passed,
        "ok": passed == len(cases),
        "cases": cases,
        "adapter_enabled": terminal_adapter_enabled(),
        "note": "Slice canaries only. Pipeline.run untouched.",
    }
    if payload["adapter_enabled"]:
        payload["ok"] = False
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_matrix(), indent=2))
