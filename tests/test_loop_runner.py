"""Flag routing + path-equivalence tests for the loop-runner extraction."""

from __future__ import annotations

import sys
from uuid import uuid4

import pytest

import core.pipeline as cp
from core.loop.handlers.finalize import FinalizeContext, FinalizeHandler, FinalizeOutcome
from core.loop.handlers.verify import VerificationOutcome
from core.pipeline import Pipeline
from core.registry import GemRegistry, build_default_registry
from core.schemas import (
    BlackTourmalineResponse,
    ClearQuartzResponse,
    Envelope,
    ExecutionPlan,
    PlanStep,
    ResponseEnvelope,
    RoseQuartzResponse,
    SeleniteResponse,
)
from scripts.shadow_runner import run_selftest


class FakeGem:
    """Minimal offline gem set (same pattern as tests/test_pipeline_mocked.py)."""

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


def test_flag_off_uses_finalize_legacy(monkeypatch):
    monkeypatch.delenv("ETHER_LOOP_RUNNER", raising=False)
    hits = {"legacy": 0}
    orig = Pipeline._finalize_legacy

    def spy(self, result, **kwargs):
        hits["legacy"] += 1
        return orig(self, result, **kwargs)

    class BoomRunner:
        def __init__(self, *a, **k):
            raise AssertionError("LoopRunner must not be constructed with the flag off")

    monkeypatch.setattr(Pipeline, "_finalize_legacy", spy)
    monkeypatch.setattr(cp, "LoopRunner", BoomRunner)

    run_pipeline = _fake_pipeline().run  # bound once: audit QUAL-003 names any *.run()
    result = run_pipeline("write hello")
    assert hits["legacy"] == 1
    assert result.status == "complete"


def test_flag_on_routes_via_loop_runner(monkeypatch):
    monkeypatch.setenv("ETHER_LOOP_RUNNER", "1")
    seen = {}

    class FakeRunner:
        def __init__(self, registry):
            seen["registry"] = registry

        def run_verify(self, ctx):
            # stage-2: the spine dispatch runs first; pass the gate values
            # through unchanged so the finalize assertions below stay valid.
            seen["verify_ctx"] = ctx
            return VerificationOutcome(
                stages=[],
                confidence=ctx.confidence,
                audit=None,
                critique=None,
                holdout_ok=None,
                holdout_test=ctx.holdout_test,
                reward=0.0,
                exit_code=ctx.sandbox_exit,
                total_tests=ctx.sandbox_total_tests,
            )

        def run_finalize(self, ctx):
            seen["ctx"] = ctx
            return FinalizeOutcome(
                status="error",
                error="injected",
                stages=[{"stage": "auto_fabricate", "success": True, "detail": "shadow"}],
                degraded=["shadow_degraded:X"],
            )

    monkeypatch.setattr(cp, "LoopRunner", FakeRunner)

    run_pipeline = _fake_pipeline().run  # bound once: audit QUAL-003 names any *.run()
    result = run_pipeline("write hello")
    assert isinstance(seen["ctx"], FinalizeContext)
    assert seen["ctx"].success is True
    assert seen["ctx"].task_id == str(result.task_id)
    # stages/status/error/degraded from the outcome are applied to the result
    assert any(s.stage == "auto_fabricate" and s.detail == "shadow" for s in result.stages)
    assert result.status == "error"
    assert result.error == "injected"
    assert "shadow_degraded:X" in result.degraded


def test_finalize_paths_equivalent():
    """The shadow harness must prove legacy and loop-runner tails identical."""
    assert run_selftest() is True


# -- handler unit tests -------------------------------------------------------


def _ctx(**overrides) -> FinalizeContext:
    kwargs = dict(
        task_id=str(uuid4()),
        objective="write f",
        generated="def f():\n    return 1\n",
        success=True,
        strategy="default",
        confidence=0.9,
        verification_score=1.0,
        total_tests=2,
        holdout_ok=True,
        tool_assist=True,
        has_sandbox=True,
        exit_code=0,
    )
    kwargs.update(overrides)
    return FinalizeContext(**kwargs)


@pytest.fixture
def quiet_boundaries(monkeypatch):
    """No-op the state-touching boundaries of the handler module."""
    monkeypatch.setattr("core.loop.handlers.finalize.record_outcome", lambda *a, **k: None)
    monkeypatch.setattr("core.loop.handlers.finalize.experience_record", lambda *a, **k: None)
    monkeypatch.setattr("core.loop.handlers.finalize.maybe_propose_fabricate", lambda: None)
    monkeypatch.setattr("core.loop.handlers.finalize.is_frozen", lambda: False)


def test_handler_fabricate_frozen_branch(quiet_boundaries, monkeypatch):
    monkeypatch.setattr(
        "core.loop.handlers.finalize.maybe_propose_fabricate",
        lambda: {"name": "x_tool", "action": "fabricate"},
    )
    monkeypatch.setattr("core.loop.handlers.finalize.is_frozen", lambda: True)
    handler = FinalizeHandler(registry=GemRegistry(), run_tool=lambda n, p: {"ok": True})
    out = handler.run(_ctx(success=False, exit_code=1, last_err="boom"))
    fab = [s for s in out.stages if s["stage"] == "auto_fabricate"]
    assert fab == [
        {"stage": "auto_fabricate", "success": False, "detail": "blocked_by_bench_guardian"}
    ]
    assert "duration_ms" not in fab[0]


def test_handler_memory_save_citrine_down(quiet_boundaries, monkeypatch):
    monkeypatch.setattr(
        "core.loop.handlers.finalize.index_pass_pattern",
        lambda **k: {"ok": False, "error": "citrine down"},
    )
    handler = FinalizeHandler(registry=GemRegistry(), run_tool=lambda n, p: {"ok": True})
    out = handler.run(_ctx())
    mem = [s for s in out.stages if s["stage"] == "memory_save"]
    assert len(mem) == 1
    assert mem[0]["success"] is False
    assert "citrine=False" in mem[0]["detail"]
    assert "error=citrine down" in mem[0]["detail"]


def test_handler_status_derivation_error_string(quiet_boundaries):
    handler = FinalizeHandler(registry=GemRegistry(), run_tool=lambda n, p: {"ok": True})
    out = handler.run(_ctx(success=False, exit_code=1, last_err="  AssertionError: boom  "))
    assert out.status == "error"
    assert out.error == "sandbox exit 1: AssertionError: boom"


def test_handler_error_none_leaves_caller_error(quiet_boundaries):
    handler = FinalizeHandler(registry=GemRegistry(), run_tool=lambda n, p: {"ok": True})
    out = handler.run(
        _ctx(success=False, exit_code=1, last_err="ignored", result_error="code failed")
    )
    assert out.status == "error"
    assert out.error is None


def test_handler_experience_failure_degrades(quiet_boundaries, monkeypatch):
    def boom(**k):
        raise RuntimeError("vault exploded")

    monkeypatch.setattr("core.loop.handlers.finalize.experience_record", boom)
    handler = FinalizeHandler(registry=GemRegistry(), run_tool=lambda n, p: {"ok": True})
    out = handler.run(_ctx())
    assert out.degraded == ["experience_record_failed:RuntimeError"]


# -- registry degraded wiring -------------------------------------------------


def test_gem_registry_degraded_defaults_empty():
    assert GemRegistry().degraded == []


def test_build_default_registry_records_citrine_loss(monkeypatch):
    # Force the citrine import to fail in every environment (qdrant present
    # or not): a None sys.modules entry halts the import with ImportError.
    monkeypatch.setitem(sys.modules, "gems.citrine.memory", None)
    monkeypatch.setitem(sys.modules, "gems.citrine", None)
    reg = build_default_registry()
    assert any(d.startswith("citrine_unavailable:") for d in reg.degraded)
    assert reg.get("citrine") is None
