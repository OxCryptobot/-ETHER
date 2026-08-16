"""Phase 2A — pipeline_score pure canary.

Clamp, degrade merge, fail/ok envelopes. No Pipeline import. Adapter stays OFF.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "pipeline_score_canary.json"


def run_matrix() -> Dict[str, Any]:
    from core.pipeline_score import (
        clamp_score,
        merge_degraded,
        terminal_fail_envelope,
        terminal_ok_envelope,
    )

    cases: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        cases.append({"name": name, "pass": ok, "detail": detail})

    add("clamp_high", clamp_score(1.5) == 1.0, str(clamp_score(1.5)))
    add("clamp_low", clamp_score(-0.2) == 0.0, str(clamp_score(-0.2)))
    add("clamp_mid", clamp_score(0.42) == 0.42, str(clamp_score(0.42)))
    add(
        "merge_dedupe",
        merge_degraded(["a", "b"], "a", "c") == ["a", "b", "c"],
        str(merge_degraded(["a", "b"], "a", "c")),
    )
    fail = terminal_fail_envelope(stage="tool_runtime", marker="tool_runtime_failed_terminal")
    add("fail_envelope_ok_false", fail.get("ok") is False)
    add("fail_envelope_marker", "tool_runtime_failed_terminal" in str(fail))
    ok_env = terminal_ok_envelope(score=0.9, degraded=["slow"])
    add("ok_envelope_ok_true", ok_env.get("ok") is True)
    add("ok_envelope_score", float(ok_env.get("score") or 0) == 0.9)

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
        "note": "Score pure canary. No Pipeline.run change.",
    }
    if payload["adapter_enabled"]:
        payload["ok"] = False
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_matrix(), indent=2))
