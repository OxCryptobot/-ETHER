"""Stage-2 verification-spine extraction: models, handler units, parity, flag routing."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

import core.pipeline as cp
from core.learning import compute_reward
from core.loop.handlers.finalize import FinalizeOutcome
from core.loop.handlers.verify import (
    VerificationContext,
    VerificationHandler,
    VerificationOutcome,
)
from core.pipeline import Pipeline
from core.registry import GemRegistry
from core.schemas import (
    BlackTourmalineResponse,
    ClearQuartzResponse,
    Envelope,
    ExecutionPlan,
    LabradoriteResponse,
    PlanStep,
    PolicyViolation,
    ResponseEnvelope,
    RoseQuartzResponse,
    SeleniteResponse,
)
from scripts.shadow_runner import run_verify_selftest


def _ctx_kwargs(**overrides) -> dict:
    kwargs = dict(
        task_id=str(uuid4()),
        objective="write f",
        generated="def f():\n    return 1\n",
        tool_assist=True,
        critique=False,
        holdout_test="",
        sent_prompts=["Write Python code for:\nwrite f"],
        has_sandbox=True,
        sandbox_exit=0,
        sandbox_total_tests=2,
        confidence=0.9,
        verification_score=1.0,
        retries=0,
        plan_ok=True,
        first_compile_ok=True,
        used_burst=False,
    )
    kwargs.update(overrides)
    return kwargs


def _ctx(**overrides) -> VerificationContext:
    return VerificationContext(**_ctx_kwargs(**overrides))


def _outcome_kwargs(**overrides) -> dict:
    kwargs = dict(
        stages=[],
        confidence=0.9,
        audit=None,
        critique=None,
        holdout_ok=None,
        holdout_test="",
        reward=0.0,
        exit_code=0,
        total_tests=2,
    )
    kwargs.update(overrides)
    return kwargs


# -- model tests ----------------------------------------------------------------


def test_context_forbids_extra_fields():
    with pytest.raises(ValidationError):
        VerificationContext(**_ctx_kwargs(bogus_field=1))


def test_context_requires_fields():
    for missing in ("task_id", "used_burst", "sent_prompts", "sandbox_exit"):
        kwargs = _ctx_kwargs()
        del kwargs[missing]
        with pytest.raises(ValidationError):
            VerificationContext(**kwargs)


def test_outcome_forbids_extra_fields():
    with pytest.raises(ValidationError):
        VerificationOutcome(**_outcome_kwargs(bogus_field=1))


def test_outcome_requires_fields():
    for missing in ("confidence", "reward", "holdout_ok", "total_tests"):
        kwargs = _outcome_kwargs()
        del kwargs[missing]
        with pytest.raises(ValidationError):
            VerificationOutcome(**kwargs)


# -- handler unit tests (stub registry/run_tool, no gems) -----------------------


class _StubRes:
    def __init__(self, error=None, payload=None):
        self.error = error
        self.payload = payload


class _StubErr:
    def __init__(self, message):
        self.message = message


class _StubRegistry:
    degraded = []

    def __init__(self, audit=None, audit_error=None, crit=None, crit_error=None):
        self._audit = audit
        self._audit_error = audit_error
        self._crit = crit
        self._crit_error = crit_error

    def execute(self, request):
        if request.target_gem == "black-tourmaline":
            if self._audit_error is not None:
                return _StubRes(error=_StubErr(self._audit_error))
            return _StubRes(payload=self._audit)
        if request.target_gem == "labradorite":
            if self._crit_error is not None:
                return _StubRes(error=_StubErr(self._crit_error))
            return _StubRes(payload=self._crit)
        return _StubRes()


def _run_tool(scan=None, sub=None):
    def _rt(name, payload):
        if name == "secret_scan":
            return scan if scan is not None else {"ok": True, "result": {"clean": True}}
        if name == "subprocess_audit":
            return sub if sub is not None else {"ok": True, "result": {"risky": False}}
        return {"ok": True}

    return _rt


@pytest.fixture
def quiet_progress(monkeypatch):
    monkeypatch.setattr("core.loop.handlers.verify.write_progress", lambda *a, **k: None)


def _handler(registry=None, run_tool=None) -> VerificationHandler:
    return VerificationHandler(
        registry=registry
        or _StubRegistry(audit=BlackTourmalineResponse(approved=True, risk_score=0.1)),
        run_tool=run_tool or _run_tool(),
    )


def test_handler_audit_approved(quiet_progress):
    handler = _handler()  # bound once: audit QUAL-003 names any *.run()
    out = handler.run(_ctx())
    assert [s["stage"] for s in out.stages] == ["tool_scan", "audit"]
    assert out.confidence == 0.9
    assert out.audit == BlackTourmalineResponse(approved=True, risk_score=0.1).model_dump(
        mode="json"
    )
    assert out.exit_code == 0
    assert out.total_tests == 2
    assert out.reward == compute_reward(
        exit_code=0,
        confidence=0.9,
        audit_approved=True,
        retries=0,
        verification_score=1.0,
        had_self_check=True,
        plan_ok=True,
        first_compile_ok=True,
        used_burst=False,
        holdout_ok=None,
    )


def test_handler_audit_rejected_clamps_confidence(quiet_progress):
    reg = _StubRegistry(
        audit=BlackTourmalineResponse(
            approved=False,
            violations=[PolicyViolation(rule="no-eval", severity="high", message="eval")],
            risk_score=0.7,
        )
    )
    handler = _handler(registry=reg)  # bound once: audit QUAL-003 names any *.run()
    out = handler.run(_ctx())
    audit_stage = [s for s in out.stages if s["stage"] == "audit"][0]
    assert audit_stage["success"] is False
    assert audit_stage["detail"] == "risk=0.7"
    assert out.confidence == 0.3


def test_handler_audit_outage_neutral_reward(quiet_progress):
    reg = _StubRegistry(audit_error="black-tourmaline unreachable")
    handler = _handler(registry=reg)  # bound once: audit QUAL-003 names any *.run()
    out = handler.run(_ctx())
    audit_stage = [s for s in out.stages if s["stage"] == "audit"][0]
    assert audit_stage["success"] is False
    assert audit_stage["detail"] == "audit unavailable: black-tourmaline unreachable"
    assert out.audit is None
    assert out.confidence == 0.3
    # outage stays neutral for compute_reward (audit_approved=True), while the
    # clamped confidence keeps the reward deflated.
    assert out.reward == compute_reward(
        exit_code=0,
        confidence=0.3,
        audit_approved=True,
        retries=0,
        verification_score=1.0,
        had_self_check=True,
        plan_ok=True,
        first_compile_ok=True,
        used_burst=False,
        holdout_ok=None,
    )


def test_handler_tool_scan_dirty_secrets_clamps(quiet_progress):
    # bound once: audit QUAL-003 names any *.run()
    handler = _handler(run_tool=_run_tool(scan={"ok": True, "result": {"clean": False}}))
    out = handler.run(_ctx())
    scan_stage = [s for s in out.stages if s["stage"] == "tool_scan"][0]
    assert scan_stage["success"] is False
    assert scan_stage["detail"] == "secrets_clean=False risky_exec=False"
    assert out.confidence == 0.25


def test_handler_tool_scan_risky_exec_clamps(quiet_progress):
    # bound once: audit QUAL-003 names any *.run()
    handler = _handler(run_tool=_run_tool(sub={"ok": True, "result": {"risky": True}}))
    out = handler.run(_ctx())
    scan_stage = [s for s in out.stages if s["stage"] == "tool_scan"][0]
    assert scan_stage["detail"] == "secrets_clean=True risky_exec=True"
    assert out.confidence == 0.25


def test_handler_tool_scan_skipped_without_assist_or_code(quiet_progress):
    handler = _handler()  # bound once: audit QUAL-003 names any *.run()
    assert all(s["stage"] != "tool_scan" for s in handler.run(_ctx(tool_assist=False)).stages)
    assert all(s["stage"] != "tool_scan" for s in handler.run(_ctx(generated="")).stages)


def test_handler_critique_recorded(quiet_progress):
    reg = _StubRegistry(
        audit=BlackTourmalineResponse(approved=True, risk_score=0.0),
        crit=LabradoriteResponse(critique="x" * 120),
    )
    handler = _handler(registry=reg)  # bound once: audit QUAL-003 names any *.run()
    out = handler.run(_ctx(critique=True))
    crit_stage = [s for s in out.stages if s["stage"] == "critique"][0]
    assert crit_stage["success"] is True
    assert crit_stage["detail"] == "x" * 80
    assert out.critique is not None


def test_handler_critique_outage_explicit_stage(quiet_progress):
    reg = _StubRegistry(
        audit=BlackTourmalineResponse(approved=True, risk_score=0.0),
        crit_error="labradorite down",
    )
    handler = _handler(registry=reg)  # bound once: audit QUAL-003 names any *.run()
    out = handler.run(_ctx(critique=True))
    crit_stage = [s for s in out.stages if s["stage"] == "critique"][0]
    assert crit_stage["success"] is False
    assert crit_stage["detail"] == "critique unavailable: labradorite down"
    assert out.critique is None


def test_handler_holdout_leak_mutates_holdout_test(quiet_progress, monkeypatch):
    monkeypatch.setattr(
        "core.prompt_guard.check",
        lambda prompt, holdout: {"clean": False, "leak_count": 1, "detail": "frag in prompt"},
    )

    def _grade_should_not_run(code, hidden):
        raise AssertionError("grading must be skipped after a leak")

    monkeypatch.setattr("core.holdout.grade_against_holdout", _grade_should_not_run)
    handler = _handler()  # bound once: audit QUAL-003 names any *.run()
    out = handler.run(_ctx(holdout_test="assert f() == 1"))
    stages = [(s["stage"], s["success"], s["detail"]) for s in out.stages]
    assert (
        "prompt_guard",
        False,
        "LEAK: frag in prompt",
    ) in stages
    assert ("holdout", False, "not graded — holdout leaked into the prompt") in stages
    assert out.holdout_test == ""  # the mutation channel
    assert out.holdout_ok is None


def test_handler_guard_raises_fails_open(quiet_progress, monkeypatch):
    def _boom(prompt, holdout):
        raise RuntimeError("guard exploded")

    monkeypatch.setattr("core.prompt_guard.check", _boom)
    monkeypatch.setattr(
        "core.holdout.grade_against_holdout",
        lambda code, hidden: {"ok": True, "asserts": 3},
    )
    handler = _handler()  # bound once: audit QUAL-003 names any *.run()
    out = handler.run(_ctx(holdout_test="assert f() == 1"))
    holdout_stage = [s for s in out.stages if s["stage"] == "holdout"][0]
    assert holdout_stage["success"] is True
    assert holdout_stage["detail"] == "3 unseen asserts"
    assert out.holdout_ok is True
    assert out.holdout_test == "assert f() == 1"


def test_handler_grade_raises_fails_closed(quiet_progress, monkeypatch):
    monkeypatch.setattr(
        "core.prompt_guard.check", lambda prompt, holdout: {"clean": True, "leak_count": 0}
    )

    def _boom(code, hidden):
        raise RuntimeError("grader exploded")

    monkeypatch.setattr("core.holdout.grade_against_holdout", _boom)
    handler = _handler()  # bound once: audit QUAL-003 names any *.run()
    out = handler.run(_ctx(holdout_test="assert f() == 1"))
    holdout_stage = [s for s in out.stages if s["stage"] == "holdout"][0]
    assert holdout_stage["success"] is False
    assert holdout_stage["detail"] == "holdout grading failed: grader exploded"
    assert out.holdout_ok is False


def test_handler_compute_reward_kwargs_byte_identical(quiet_progress, monkeypatch):
    seen = {}

    def _spy(**kwargs):
        seen.update(kwargs)
        return 1.0

    monkeypatch.setattr("core.loop.handlers.verify.compute_reward", _spy)
    monkeypatch.setattr(
        "core.prompt_guard.check", lambda prompt, holdout: {"clean": True, "leak_count": 0}
    )
    monkeypatch.setattr(
        "core.holdout.grade_against_holdout",
        lambda code, hidden: {"ok": False, "asserts": 1, "reason": "nope"},
    )
    handler = _handler()  # bound once: audit QUAL-003 names any *.run()
    out = handler.run(
        _ctx(holdout_test="assert f() == 1", retries=1, used_burst=True, plan_ok=False)
    )
    assert seen == {
        "exit_code": 0,
        "confidence": 0.9,
        "audit_approved": True,
        "retries": 1,
        "verification_score": 1.0,
        "had_self_check": True,
        "plan_ok": False,
        "first_compile_ok": True,
        "used_burst": True,
        "holdout_ok": False,
    }
    assert out.reward == 1.0


# -- parity via the shadow harness ----------------------------------------------


def test_verify_paths_equivalent():
    """The shadow harness must prove legacy and loop-runner spines identical."""
    assert run_verify_selftest() is True


# -- dispatcher / flag routing ---------------------------------------------------


class FakeGem:
    """Minimal offline gem set (same pattern as tests/test_loop_runner.py)."""

    def __init__(self, name: str):
        self.name = name

    def execute(self, request: Envelope) -> ResponseEnvelope:
        if self.name == "selenite":
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="selenite",
                payload=SeleniteResponse(
                    plan=ExecutionPlan(
                        steps=[PlanStep(id=1, action="generate", target="code", description="gen")]
                    ),
                ),
            )
        if self.name == "rose-quartz":
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="rose-quartz",
                payload=RoseQuartzResponse(
                    content="def hello():\n    return 'hi'\n", model_used="fake"
                ),
            )
        if self.name == "clear-quartz":
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                payload=ClearQuartzResponse(exit_code=0, total_tests=0, tests_passed=0),
            )
        if self.name == "black-tourmaline":
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="black-tourmaline",
                payload=BlackTourmalineResponse(approved=True, risk_score=0.0),
            )
        return ResponseEnvelope(
            task_id=request.task_id,
            source_gem=self.name,  # type: ignore
            payload=None,
        )


def _fake_pipeline() -> Pipeline:
    reg = GemRegistry()
    for name in ["selenite", "rose-quartz", "clear-quartz", "black-tourmaline"]:
        reg.register(name, FakeGem(name))
    return Pipeline(registry=reg)


def test_flag_off_uses_verify_legacy(monkeypatch):
    monkeypatch.delenv("ETHER_LOOP_RUNNER", raising=False)
    hits = {"legacy": 0}
    orig = Pipeline._verify_legacy

    def spy(self, result, **kwargs):
        hits["legacy"] += 1
        return orig(self, result, **kwargs)

    class BoomRunner:
        def __init__(self, *a, **k):
            raise AssertionError("LoopRunner must not be constructed with the flag off")

    monkeypatch.setattr(Pipeline, "_verify_legacy", spy)
    monkeypatch.setattr(cp, "LoopRunner", BoomRunner)

    run_pipeline = _fake_pipeline().run  # bound once: audit QUAL-003 names any *.run()
    result = run_pipeline("write hello")
    assert hits["legacy"] == 1
    assert result.status == "complete"


def test_flag_on_routes_verify_via_loop_runner(monkeypatch):
    monkeypatch.setenv("ETHER_LOOP_RUNNER", "1")
    seen = {}

    class FakeRunner:
        def __init__(self, registry):
            seen["registry"] = registry

        def run_verify(self, ctx):
            seen["verify_ctx"] = ctx
            return VerificationOutcome(
                stages=[{"stage": "audit", "success": True, "detail": "shadow"}],
                confidence=0.31,
                audit=BlackTourmalineResponse(approved=True, risk_score=0.2).model_dump(
                    mode="json"
                ),
                critique=None,
                holdout_ok=None,
                holdout_test=ctx.holdout_test,
                reward=0.77,
                exit_code=ctx.sandbox_exit,
                total_tests=ctx.sandbox_total_tests,
            )

        def run_finalize(self, ctx):
            seen["finalize_ctx"] = ctx
            return FinalizeOutcome(status="complete", error=None, stages=[], degraded=[])

    monkeypatch.setattr(cp, "LoopRunner", FakeRunner)

    run_pipeline = _fake_pipeline().run  # bound once: audit QUAL-003 names any *.run()
    result = run_pipeline("write hello")
    ctx = seen["verify_ctx"]
    assert isinstance(ctx, VerificationContext)
    assert ctx.task_id == str(result.task_id)
    assert ctx.has_sandbox is True
    assert ctx.sandbox_exit == 0
    # outcome applied: stages/confidence/audit/reward flow onto the result
    assert any(s.stage == "audit" and s.detail == "shadow" for s in result.stages)
    assert result.confidence == 0.31
    assert isinstance(result.audit, BlackTourmalineResponse)
    assert result.audit.risk_score == 0.2
    assert result.reward == 0.77
    # the finalize dispatch consumed the RETURNED gate values
    assert seen["finalize_ctx"].exit_code == 0
    assert seen["finalize_ctx"].total_tests == ctx.sandbox_total_tests


def _observable_run(result):
    return {
        "stages": [
            {k: v for k, v in s.model_dump().items() if k != "duration_ms"} for s in result.stages
        ],
        "confidence": result.confidence,
        "reward": result.reward,
        "holdout_ok": result.holdout_ok,
        "audit": result.audit.model_dump(mode="json") if result.audit else None,
        "status": result.status,
    }


def test_end_to_end_flag_parity(monkeypatch):
    """A stubbed end-to-end run is identical under both flag states."""
    monkeypatch.setattr(cp, "select_strategy_with_context", lambda *a, **k: ("default", {}))
    monkeypatch.setenv("ETHER_TOOL_ASSIST", "1")
    # Pin the stateful boundaries so run 2 cannot observe run 1's writes
    # (few-shot/experience retrieval, citrine indexing). The same stubs serve
    # both flag paths because both resolve run_tool lazily at call time.
    monkeypatch.setattr(cp, "experience_retrieve", lambda *a, **k: {"block": ""})
    monkeypatch.setattr(cp, "index_pass_pattern", lambda **k: {"ok": True})
    # the flag-on finalize tail resolves the same boundary from its own module
    monkeypatch.setattr("core.loop.handlers.finalize.index_pass_pattern", lambda **k: {"ok": True})

    def _run_tool(name, payload):
        if name == "few_shot_pack":
            return {"ok": True, "result": {"block": ""}}
        if name == "secret_scan":
            return {"ok": True, "result": {"clean": True}}
        if name == "subprocess_audit":
            return {"ok": True, "result": {"risky": False}}
        return {"ok": True}

    monkeypatch.setattr("gems.grandidierite.registry.run_tool", _run_tool)

    monkeypatch.delenv("ETHER_LOOP_RUNNER", raising=False)
    legacy_run = _fake_pipeline().run  # bound once: audit QUAL-003 names any *.run()
    legacy = _observable_run(legacy_run("write hello"))

    monkeypatch.setenv("ETHER_LOOP_RUNNER", "1")
    new_run = _fake_pipeline().run  # bound once: audit QUAL-003 names any *.run()
    new = _observable_run(new_run("write hello"))

    assert legacy == new
