"""Grade generated code against assertions it never saw.

This is the only verification in @ETHER that a model cannot game by writing its
own tests. Everything else — `total_tests`, `verification_score`, the flywheel
`conf=1.000` — is derived from assertions the generator authored about its own
output. Even with `core/assert_audit.py` rejecting tautologies and swallowed
failures, self-authored tests only prove the code does what the model *intended*.

Held-out grading appends assertions from a separate dataset (the generator is
prompted with the signature only) and re-runs the combination in the sandbox.

The primitive lived inline in `scripts/hidden_quiz.py` and was wired to nothing.
"""

from __future__ import annotations

import ast
from typing import Any, Dict
from uuid import uuid4

from core.assert_audit import count_real_asserts


def strip_module_level_asserts(code: str) -> str:
    """Remove top-level `assert` statements from generated code.

    The holdout is appended after the model's own code, so a self-authored
    assertion executes FIRST. If it fails, the program exits before the
    held-out assertions ever run and a correct implementation is reported as
    "holdout assertions failed" — a false negative attributed to the wrong
    cause. `core/autonomy.py::ensure_assert_objective` explicitly instructs
    the model to write such assertions, so this is the common case, not an
    edge case.

    Only module-level assertions are removed. Assertions inside a function
    body are left alone: those are the implementation's own preconditions, and
    if the holdout trips one that is a genuine failure of the code under test.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    kept = [node for node in tree.body if not isinstance(node, ast.Assert)]
    if len(kept) == len(tree.body):
        return code
    tree.body = kept
    try:
        return ast.unparse(tree)
    except Exception:
        return code


def grade_against_holdout(
    code: str, hidden_test: str, timeout: int = 60
) -> Dict[str, Any]:
    """Run `code` against `hidden_test` and report whether it genuinely passes.

    Returns a dict with:
      ok        — True only if the combined program exits 0 AND the holdout
                  contributed at least one real assertion
      asserts   — number of observable assertions the holdout contributed
      leaked    — True if `code` already contains the holdout text, which
                  would make the grade meaningless
      reason    — why the grade is not usable, when ok is False

    Fails closed: any error grading is `ok=False`, never a pass.
    """
    result: Dict[str, Any] = {
        "ok": False,
        "exit_code": None,
        "asserts": 0,
        "leaked": False,
        "reached_end": False,
        "reason": "",
        "stderr": "",
    }

    if not (code or "").strip():
        result["reason"] = "no generated code"
        return result
    if not (hidden_test or "").strip():
        result["reason"] = "no holdout test"
        return result

    # A holdout made of tautologies grades nothing.
    holdout_asserts = count_real_asserts(hidden_test)
    result["asserts"] = holdout_asserts
    if holdout_asserts < 1:
        result["reason"] = "holdout contributes no observable assertions"
        return result

    # If the generator was somehow shown the holdout, the grade is worthless.
    normalized = " ".join(hidden_test.split())
    if normalized and normalized in " ".join(code.split()):
        result["leaked"] = True
        result["reason"] = "holdout text present in generated code (leaked)"
        return result

    # Strip the model's own top-level assertions so they cannot abort the
    # program before the held-out ones run. Without this a correct
    # implementation carrying one bad self-assert grades as a holdout failure.
    graded_code = strip_module_level_asserts(code)

    # Exit code alone is NOT proof the assertions ran. `sys.exit(0)`,
    # `os._exit(0)`, `raise SystemExit(0)`, an atexit hook or a replaced
    # sys.excepthook all produce a clean exit while the held-out assertions
    # either never execute or fail silently — every one of those made a
    # deliberately wrong implementation grade as a pass.
    #
    # The sentinel is emitted as the LAST statement after the assertions, and
    # its value is unpredictable to the generator, so it can only appear in
    # stdout if control actually reached the end of the holdout block.
    sentinel = f"__ETHER_HOLDOUT_OK_{uuid4().hex}__"
    combined = (
        graded_code.rstrip()
        + "\n\n# holdout tests (unseen by the generator)\n"
        + hidden_test
        + f"\nprint({sentinel!r})\n"
    )

    try:
        from core.registry import build_default_registry
        from core.schemas import ClearQuartzRequest, Envelope

        response = build_default_registry().execute(
            Envelope(
                task_id=uuid4(),
                target_gem="clear-quartz",
                payload=ClearQuartzRequest(code=combined),
                timeout_seconds=timeout,
            )
        )
    except Exception as e:  # sandbox unavailable -> not a pass
        result["reason"] = f"sandbox error: {e}"
        return result

    if response.error or response.payload is None:
        result["reason"] = (
            f"sandbox error: {response.error.message}" if response.error else "no sandbox payload"
        )
        return result

    payload = response.payload
    result["exit_code"] = payload.exit_code
    result["stderr"] = (payload.stderr or "")[-500:]

    reached_end = sentinel in (payload.stdout or "")
    result["reached_end"] = reached_end
    result["ok"] = payload.exit_code == 0 and reached_end

    if not result["ok"]:
        if payload.exit_code != 0:
            result["reason"] = "holdout assertions failed"
        else:
            # Clean exit without the sentinel: the program terminated before
            # the assertions completed.
            result["reason"] = "exited before the holdout assertions completed"
    return result
