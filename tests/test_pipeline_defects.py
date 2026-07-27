"""Regression tests for confirmed Pipeline/registry defects.

Each test here pins a bug that shipped green: a run that failed reporting
"complete", a bandit whose context features were never passed, a fabricate
stage hardcoded to success, audit/critique rows that vanished on a gem
outage, and an exception stage whose duration was always ~0ms.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

from core.pipeline import Pipeline
from core.registry import GemRegistry
from core.schemas import (
    AmethystResponse,
    BlackTourmalineResponse,
    ClearQuartzResponse,
    Envelope,
    ExecutionPlan,
    GemError,
    GemErrorType,
    LabradoriteResponse,
    PlanStep,
    ResponseEnvelope,
    RoseQuartzResponse,
    SeleniteResponse,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _plan_response(request: Envelope) -> ResponseEnvelope:
    return ResponseEnvelope(
        task_id=request.task_id,
        source_gem="selenite",
        payload=SeleniteResponse(
            plan=ExecutionPlan(
                steps=[PlanStep(id=1, action="generate", target="code", description="gen")]
            )
        ),
    )


class ScriptedGem:
    """Gem whose response for a given target is supplied by the test."""

    def __init__(self, name: str, responder):
        self.name = name
        self.responder = responder
        self.calls = 0

    def execute(self, request: Envelope) -> ResponseEnvelope:
        self.calls += 1
        return self.responder(request)


def _error(request: Envelope, gem: str, msg: str) -> ResponseEnvelope:
    return ResponseEnvelope(
        task_id=request.task_id,
        source_gem=gem,  # type: ignore[arg-type]
        error=GemError(type=GemErrorType.RUNTIME, message=msg, recoverable=True),
    )


def build_registry(
    *,
    sandbox_exit: int = 0,
    sandbox_stderr: str = "",
    audit: str = "approve",  # "approve" | "reject" | "error"
    critique: str = "ok",  # "ok" | "error"
    grandidierite: str = "ok",  # "ok" | "error" | "absent"
) -> GemRegistry:
    reg = GemRegistry()
    reg.register("selenite", ScriptedGem("selenite", _plan_response))
    reg.register(
        "rose-quartz",
        ScriptedGem(
            "rose-quartz",
            lambda r: ResponseEnvelope(
                task_id=r.task_id,
                source_gem="rose-quartz",
                payload=RoseQuartzResponse(content="def hello():\n    return 'hi'\n", model_used="fake"),
            ),
        ),
    )
    reg.register(
        "clear-quartz",
        ScriptedGem(
            "clear-quartz",
            lambda r: ResponseEnvelope(
                task_id=r.task_id,
                source_gem="clear-quartz",
                payload=ClearQuartzResponse(
                    exit_code=sandbox_exit,
                    total_tests=0,
                    tests_passed=0,
                    stderr=sandbox_stderr,
                ),
            ),
        ),
    )

    def _audit(r: Envelope) -> ResponseEnvelope:
        if audit == "error":
            return _error(r, "black-tourmaline", "black-tourmaline unreachable")
        return ResponseEnvelope(
            task_id=r.task_id,
            source_gem="black-tourmaline",
            payload=BlackTourmalineResponse(approved=(audit == "approve"), risk_score=0.0),
        )

    reg.register("black-tourmaline", ScriptedGem("black-tourmaline", _audit))

    def _critique(r: Envelope) -> ResponseEnvelope:
        if critique == "error":
            return _error(r, "labradorite", "labradorite unreachable")
        return ResponseEnvelope(
            task_id=r.task_id,
            source_gem="labradorite",
            payload=LabradoriteResponse(critique="looks fine"),
        )

    reg.register("labradorite", ScriptedGem("labradorite", _critique))
    reg.register(
        "amethyst",
        ScriptedGem(
            "amethyst",
            lambda r: ResponseEnvelope(
                task_id=r.task_id, source_gem="amethyst", payload=AmethystResponse(status="logged")
            ),
        ),
    )

    if grandidierite != "absent":

        def _grand(r: Envelope) -> ResponseEnvelope:
            if grandidierite == "error":
                return _error(r, "grandidierite", "fabricate refused")
            return ResponseEnvelope(
                task_id=r.task_id, source_gem="grandidierite", payload=AmethystResponse(status="ok")
            )

        reg.register("grandidierite", ScriptedGem("grandidierite", _grand))
    return reg


@pytest.fixture(autouse=True)
def _quiet_env(monkeypatch):
    """Keep runs hermetic and single-attempt unless a test says otherwise."""
    monkeypatch.setenv("ETHER_TOOL_ASSIST", "0")
    monkeypatch.setenv("ETHER_CONTEXT", "0")
    monkeypatch.setenv("ETHER_SANDBOX_RETRY", "0")
    monkeypatch.setenv("ETHER_AUTO_FABRICATE_ON_FAIL", "0")


def _stage(result, name):
    return next((s for s in result.stages if s.stage == name), None)


# --------------------------------------------------------------------------
# Defect 1 — status must be derived from the sandbox result
# --------------------------------------------------------------------------


def test_status_is_not_complete_when_sandbox_never_succeeds():
    """`result.status = "complete"` was unconditional.

    cli/main.py does `Exit(0 if result.status == "complete" else 1)`, so
    `ether run` exited 0 on a run whose generated code never executed.
    """
    result = Pipeline(registry=build_registry(sandbox_exit=1, sandbox_stderr="boom")).run("write hello")

    assert result.sandbox is not None
    assert result.sandbox.exit_code == 1
    assert result.status != "complete"
    assert result.status == "error"
    # The CLI exit-code predicate, verbatim.
    assert (0 if result.status == "complete" else 1) == 1
    # And the operator gets a reason rather than an empty Error panel.
    assert result.error and "boom" in result.error


def test_status_is_complete_on_a_clean_run():
    result = Pipeline(registry=build_registry(sandbox_exit=0)).run("write hello")
    assert result.status == "complete"
    assert result.error is None
    assert (0 if result.status == "complete" else 1) == 0


@pytest.mark.parametrize("exit_code,expected_ok", [(0, True), (1, False), (2, False)])
def test_downstream_success_gates_agree_with_status(exit_code, expected_ok):
    """The `status == "complete" and sandbox.exit_code == 0` gate used by
    scripts/{bench,quiz,batch_worker,compare_run,burst_ablation,compare_runners}
    must not change meaning, and must now agree with status alone."""
    r = Pipeline(registry=build_registry(sandbox_exit=exit_code)).run("write hello")
    gate = r.status == "complete" and bool(r.sandbox) and r.sandbox.exit_code == 0
    assert gate is expected_ok
    # dashboard/collector.py buckets on complete/error only — stay exhaustive
    # so pipeline_success_rate = complete/(complete+error) counts every run.
    assert r.status in ("complete", "error")


# --------------------------------------------------------------------------
# Defect 2 — dead modules / unwired bandit context
# --------------------------------------------------------------------------


def test_registry_no_longer_imports_a_nonexistent_symbol():
    """`from core.pipeline_boot import apply` raised ImportError on every
    build_default_registry() call and was swallowed by a bare except.

    Checked against the AST, not the text, so the explanatory comment left
    behind in registry.py does not satisfy the test.
    """
    import ast
    from pathlib import Path

    import core.registry as registry_mod

    tree = ast.parse(Path(registry_mod.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)

    assert not any(m.startswith("core.pipeline_boot") for m in imported)
    # Every module registry.py imports must actually be importable.
    import importlib

    for mod in imported:
        importlib.import_module(mod)


@pytest.mark.parametrize("mod", ["core.pipeline_boot", "core.pipeline_patch", "core.intel_runtime"])
def test_dead_duplicate_modules_are_gone(mod):
    """Three near-identical copies of select_strategy with zero live callers."""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(mod)


def test_bandit_select_receives_context_features(monkeypatch):
    """Pipeline.run called self.policy.select() with no argument, so
    BanditPolicy.select's multifile/fail_kind/tier branches never fired."""
    seen: List[Optional[Dict[str, Any]]] = []

    class RecordingPolicy:
        def select(self, context=None):
            seen.append(context)
            return "default"

        def update(self, strategy, reward):
            pass

    monkeypatch.setenv("ETHER_LEARNING", "1")
    pipe = Pipeline(registry=build_registry())
    pipe.policy = RecordingPolicy()  # type: ignore[assignment]
    pipe.run("refactor the parser module into a package")

    assert seen, "policy.select was never called"
    ctx = seen[0]
    assert ctx is not None, "select() was still called with no context"
    assert set(ctx) >= {"tier", "fail_kind", "multifile"}
    # "refactor"/"module"/"package" -> the multifile feature must fire.
    assert ctx["multifile"] is True


def test_bandit_context_multifile_is_objective_sensitive(monkeypatch):
    seen: List[Optional[Dict[str, Any]]] = []

    class RecordingPolicy:
        def select(self, context=None):
            seen.append(context)
            return "default"

        def update(self, strategy, reward):
            pass

    monkeypatch.setenv("ETHER_LEARNING", "1")
    pipe = Pipeline(registry=build_registry())
    pipe.policy = RecordingPolicy()  # type: ignore[assignment]
    pipe.run("add two numbers")
    assert seen[0] is not None
    assert seen[0]["multifile"] is False


def test_learning_disabled_still_short_circuits_to_default(monkeypatch):
    monkeypatch.setenv("ETHER_LEARNING", "0")

    class ExplodingPolicy:
        def select(self, context=None):
            raise AssertionError("policy must not be consulted when learning is off")

        def update(self, strategy, reward):
            raise AssertionError("policy must not be updated when learning is off")

    pipe = Pipeline(registry=build_registry())
    pipe.policy = ExplodingPolicy()  # type: ignore[assignment]
    result = pipe.run("write hello")
    assert result.strategy == "default"


# --------------------------------------------------------------------------
# Defect 3 — auto_fabricate hardcoded success=True on the failure path
# --------------------------------------------------------------------------


def _force_fabricate(monkeypatch):
    monkeypatch.setenv("ETHER_AUTO_FABRICATE_ON_FAIL", "1")
    monkeypatch.setenv("ETHER_FAIL_STREAK_THRESHOLD", "1")
    monkeypatch.setenv("ETHER_FABRICATE_STUB_ONLY", "1")
    import core.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "is_frozen", lambda: False)


def _registry_failing_at_plan(grandidierite: str) -> GemRegistry:
    reg = build_registry(grandidierite=grandidierite)
    reg.register("selenite", ScriptedGem("selenite", lambda r: _error(r, "selenite", "plan boom")))
    return reg


def test_auto_fabricate_on_fail_path_reports_gem_error(monkeypatch):
    """The _fail() path discarded the response envelope and hardcoded
    success=True, so a fabricate that errored still logged a green stage."""
    _force_fabricate(monkeypatch)
    result = Pipeline(registry=_registry_failing_at_plan("error")).run("write hello")

    assert result.status == "error"
    fab = _stage(result, "auto_fabricate")
    assert fab is not None, "auto_fabricate stage did not run"
    assert fab.success is False
    assert "refused" in fab.detail


def test_auto_fabricate_on_fail_path_reports_success_when_it_works(monkeypatch):
    _force_fabricate(monkeypatch)
    result = Pipeline(registry=_registry_failing_at_plan("ok")).run("write hello")

    fab = _stage(result, "auto_fabricate")
    assert fab is not None
    assert fab.success is True


def test_auto_fabricate_success_and_failure_paths_agree(monkeypatch):
    """Both call sites must derive success identically from the envelope."""
    from core.fail_streak import record_outcome

    _force_fabricate(monkeypatch)
    # failure path (_fail): plan blows up
    failed = Pipeline(registry=_registry_failing_at_plan("error")).run("write hello")
    # A proposal is only made once per streak; reset so the second run also
    # reaches its auto_fabricate branch.
    record_outcome(True)
    # run-body path: sandbox non-zero, fabricate errors
    ran = Pipeline(registry=build_registry(sandbox_exit=1, grandidierite="error")).run("write hello")

    a = _stage(failed, "auto_fabricate")
    b = _stage(ran, "auto_fabricate")
    assert a is not None and b is not None
    assert a.success == b.success is False


# --------------------------------------------------------------------------
# Defect 4 — audit / critique vanishing silently on gem error
# --------------------------------------------------------------------------


def test_audit_gem_outage_produces_an_explicit_failed_stage():
    """`if not audit_res.error and isinstance(...)` had no else: a gem outage
    produced no StageResult at all and skipped the confidence clamp."""
    result = Pipeline(registry=build_registry(audit="error")).run("write hello")

    audit = _stage(result, "audit")
    assert audit is not None, "audit stage vanished on gem error"
    assert audit.success is False
    assert "unavailable" in audit.detail
    assert "unreachable" in audit.detail
    assert result.audit is None


def test_audit_gem_outage_clamps_confidence():
    ok = Pipeline(registry=build_registry(audit="approve")).run("write hello")
    down = Pipeline(registry=build_registry(audit="error")).run("write hello")

    assert down.confidence <= 0.3
    assert down.confidence <= ok.confidence


def test_audit_gem_outage_does_not_train_the_bandit_to_punish_good_code():
    """audit_ok computed False on an outage, and compute_reward turns
    audit_approved=False into a flat -0.2 — punishing code the auditor never
    saw. An absent verdict must not be read as a rejection."""
    rejected = Pipeline(registry=build_registry(audit="reject")).run("write hello")
    outage = Pipeline(registry=build_registry(audit="error")).run("write hello")

    assert rejected.reward == pytest.approx(-0.2), "a real rejection must still be penalised"
    assert outage.reward != pytest.approx(-0.2)
    assert outage.reward > rejected.reward


def test_audit_rejection_path_is_unchanged():
    result = Pipeline(registry=build_registry(audit="reject")).run("write hello")
    audit = _stage(result, "audit")
    assert audit is not None
    assert audit.success is False
    assert result.audit is not None and result.audit.approved is False
    assert result.confidence <= 0.3


def test_critique_gem_outage_produces_an_explicit_failed_stage():
    result = Pipeline(registry=build_registry(critique="error")).run("write hello", critique=True)

    crit = _stage(result, "critique")
    assert crit is not None, "critique stage vanished on gem error"
    assert crit.success is False
    assert "unavailable" in crit.detail
    assert result.critique is None


def test_critique_happy_path_is_unchanged():
    result = Pipeline(registry=build_registry(critique="ok")).run("write hello", critique=True)
    crit = _stage(result, "critique")
    assert crit is not None and crit.success is True
    assert result.critique is not None


def test_no_critique_stage_when_critique_not_requested():
    result = Pipeline(registry=build_registry(critique="error")).run("write hello")
    assert _stage(result, "critique") is None


# --------------------------------------------------------------------------
# Defect 5 — _fail() recorded a ~0ms duration for the exception stage
# --------------------------------------------------------------------------


SLEEP_S = 0.05


def test_exception_stage_records_real_elapsed_time():
    """_fail() was called as `self._fail(..., time.perf_counter())`, measuring
    the interval from "now" to "now"."""

    def _slow_then_mismatch(request: Envelope) -> ResponseEnvelope:
        time.sleep(SLEEP_S)
        # A task_id mismatch makes Orchestrator.process_response raise, which
        # is the only path that reaches the bare `except Exception` in run().
        return ResponseEnvelope(
            task_id=uuid4(),
            source_gem="selenite",
            payload=SeleniteResponse(
                plan=ExecutionPlan(
                    steps=[PlanStep(id=1, action="generate", target="code", description="g")]
                )
            ),
        )

    reg = build_registry()
    reg.register("selenite", ScriptedGem("selenite", _slow_then_mismatch))
    result = Pipeline(registry=reg).run("write hello")

    assert result.status == "error"
    exc = _stage(result, "exception")
    assert exc is not None, "no exception stage recorded"
    assert exc.success is False
    # Previously this was ~0.0 no matter how long the run took.
    assert exc.duration_ms >= SLEEP_S * 1000 * 0.8, f"duration_ms={exc.duration_ms}"


def test_stage_failures_still_report_their_own_stage_duration():
    """Non-exception _fail() call sites keep using their own stage start."""
    reg = build_registry()
    reg.register("selenite", ScriptedGem("selenite", lambda r: _error(r, "selenite", "plan boom")))
    result = Pipeline(registry=reg).run("write hello")

    plan = _stage(result, "plan")
    assert plan is not None and plan.success is False
    assert plan.duration_ms >= 0.0
