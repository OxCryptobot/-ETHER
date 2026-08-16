"""Pure sandbox code prep (strangler slice).

Multifile / synth / harness / patch cycle. No Pipeline import.
"""
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


def prepare_code_for_sandbox(code: str, objective: str = "") -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "synth": False,
        "harness": False,
        "patch": None,
        "multifile": None,
    }
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
