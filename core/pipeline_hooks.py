"""Pipeline helpers — bandit context + sandbox prep including multifile."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Tuple

_NO_PREP: ContextVar[bool] = ContextVar("ether_no_code_prep", default=False)


def code_prep_disabled() -> bool:
    return bool(_NO_PREP.get())


@contextmanager
def no_code_prep() -> Iterator[None]:
    """Run the sandbox on verbatim code — no synthesis, harness, or multifile."""
    token = _NO_PREP.set(True)
    try:
        yield
    finally:
        _NO_PREP.reset(token)


def bandit_context(objective: str, tier: int = 0, fail_kind: str = "") -> Dict[str, Any]:
    try:
        from core.multifile import is_multifile_objective

        multifile = is_multifile_objective(objective)
    except Exception:
        o = (objective or "").lower()
        multifile = any(
            k in o for k in ("class", "module", "refactor", "file", "package", "multi")
        )
    return {"tier": tier, "fail_kind": fail_kind, "multifile": multifile}


def prepare_code_for_sandbox(code: str, objective: str = "") -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {"synth": False, "harness": False, "patch": None, "multifile": None}
    if code_prep_disabled():
        meta["bypassed"] = True
        return code, meta
    try:
        from core.multifile import is_multifile_objective, run_multifile_cycle

        if is_multifile_objective(objective) or "# file:" in (code or ""):
            code2, mm = run_multifile_cycle(code)
            meta["multifile"] = mm
            code = code2
    except Exception as e:
        meta["multifile_error"] = str(e)[:120]
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


def apply_repo_oracle_gate(
    generated: str,
    objective: str,
    *,
    execution_score: float,
    verification_score: float,
    confidence: float,
) -> dict:
    """Phase B: after sandbox exit=0, optionally fail on project pytest.

    Returns dict with keys: active, ok, score, verification_score, confidence,
    last_err, fail_kind, detail. When active is False, caller ignores the rest.
    """
    try:
        from core.repo_oracle_hook import evaluate_after_sandbox

        o = evaluate_after_sandbox(generated, objective)
    except Exception as e:
        o = {
            "ok": False,
            "score": 0.0,
            "error": f"hook crash: {e}"[:200],
            "enabled": True,
        }
    if o is None or not o.get("enabled"):
        return {"active": False}
    o_ok = bool(o.get("ok"))
    o_score = float(o.get("score") or 0.0)
    ver = min(float(verification_score or 1.0), o_score)
    conf = min(
        float(confidence or 1.0),
        0.4 * float(execution_score or 0.0) + 0.6 * o_score,
    )
    detail = (
        f"score={o_score} fixture={o.get('fixture', '')}"
        + (f" err={o.get('error')}" if o.get("error") else "")
    )[:240]
    last_err = ""
    fail_kind = ""
    if not o_ok:
        last_err = (
            o.get("stderr") or o.get("stdout") or o.get("error") or "repo_oracle failed"
        )[:1500]
        fail_kind = "repo_oracle"
    return {
        "active": True,
        "ok": o_ok,
        "score": o_score,
        "verification_score": ver,
        "confidence": conf,
        "last_err": last_err,
        "fail_kind": fail_kind,
        "detail": detail,
        "repo_oracle_ok": o_ok,
    }
