"""Phase 2A — terminal decision canary (no Pipeline.run wire).

Runs a fixed matrix of decide_terminal cases and writes parity report.
Does not set ETHER_PIPELINE_TERMINAL. Does not lift wheels.
Safe under ARCH_GO + wheels ON.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "pipeline_terminal_canary.json"


def _case(
    name: str,
    *,
    tool_runtime_enabled: bool,
    tool_runtime_done: bool,
    score: float = 0.0,
    degraded: List[str] | None = None,
    error: str = "",
    expect_ok: bool,
    expect_fail: bool,
) -> Dict[str, Any]:
    from core.pipeline_terminal import decide_terminal

    out = decide_terminal(
        tool_runtime_enabled=tool_runtime_enabled,
        tool_runtime_done=tool_runtime_done,
        score=score,
        degraded=degraded,
        error=error,
    )
    ok_match = bool(out.get("ok")) is expect_ok
    fail_match = bool(out.get("should_fail")) is expect_fail
    return {
        "name": name,
        "pass": ok_match and fail_match,
        "expect_ok": expect_ok,
        "expect_fail": expect_fail,
        "got_ok": out.get("ok"),
        "got_fail": out.get("should_fail"),
        "marker": out.get("marker"),
        "reason": out.get("reason"),
    }


def run_matrix() -> Dict[str, Any]:
    cases = [
        _case(
            "tool_enabled_not_done_fails",
            tool_runtime_enabled=True,
            tool_runtime_done=False,
            expect_ok=False,
            expect_fail=True,
        ),
        _case(
            "tool_enabled_done_ok",
            tool_runtime_enabled=True,
            tool_runtime_done=True,
            score=1.0,
            expect_ok=True,
            expect_fail=False,
        ),
        _case(
            "tool_disabled_passthrough",
            tool_runtime_enabled=False,
            tool_runtime_done=False,
            score=0.8,
            expect_ok=True,
            expect_fail=False,
        ),
        _case(
            "tool_done_with_degraded",
            tool_runtime_enabled=True,
            tool_runtime_done=True,
            score=0.5,
            degraded=["slow"],
            expect_ok=True,
            expect_fail=False,
        ),
        _case(
            "error_string_still_done",
            tool_runtime_enabled=True,
            tool_runtime_done=True,
            score=0.9,
            error="warn",
            expect_ok=True,
            expect_fail=False,
        ),
    ]
    passed = sum(1 for c in cases if c["pass"])
    from core.pipeline_adapter import terminal_adapter_enabled

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "2A",
        "n": len(cases),
        "passed": passed,
        "ok": passed == len(cases),
        "cases": cases,
        "adapter_enabled": terminal_adapter_enabled(),
        "adapter_must_stay_off": True,
        "wheels_on": (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0",
        "note": (
            "Canary only — pure terminal matrix. "
            "No Pipeline.run body change. Adapter flag default OFF."
        ),
    }
    if payload["adapter_enabled"]:
        payload["ok"] = False
        payload["note"] = "FAIL: adapter unexpectedly ON during canary"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_matrix(), indent=2))
