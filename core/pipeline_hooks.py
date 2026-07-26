"""Pipeline helpers — bandit context + sandbox prep."""

from __future__ import annotations

from typing import Any, Dict, Tuple


def bandit_context(objective: str, tier: int = 0, fail_kind: str = "") -> Dict[str, Any]:
    o = (objective or "").lower()
    multifile = any(k in o for k in ("class", "module", "refactor", "file", "package", "multi"))
    return {"tier": tier, "fail_kind": fail_kind, "multifile": multifile}


def prepare_code_for_sandbox(code: str, objective: str = "") -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {"synth": False, "harness": False, "patch": None}
    try:
        from core.test_synth import synthesize_asserts

        code2, mod = synthesize_asserts(code, objective=objective)
        if mod:
            code = code2
            meta["synth"] = True
    except Exception as e:
        meta["synth_error"] = str(e)[:120]
    try:
        from core.assert_harness import ensure_harness

        code2, mod = ensure_harness(code)
        if mod:
            code = code2
            meta["harness"] = True
    except Exception as e:
        meta["harness_error"] = str(e)[:120]
    try:
        from core.patch_loop import maybe_patch_cycle

        report, code = maybe_patch_cycle(code)
        if report is not None:
            meta["patch"] = report
    except Exception as e:
        meta["patch_error"] = str(e)[:120]
    return code, meta
