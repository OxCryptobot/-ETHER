"""Stage-level shadow differ for the strangler-fig migration.

Stage 1: runs synthetic finalize scenarios through BOTH finalize paths — the
legacy inline tail (`Pipeline._finalize_legacy`) and the extracted
`LoopRunner.run_finalize` — against identical stubbed boundaries, and diffs
the observable result: stages (excluding duration_ms), status, error,
degraded, plus the side-effect call logs of every stubbed boundary.

Stage 2: runs synthetic verification-spine scenarios through BOTH spine
paths — the legacy inline block (`Pipeline._verify_legacy`) and the
extracted `LoopRunner.run_verify` — and diffs: appended stages (minus
duration_ms), confidence, audit/critique payloads, holdout_ok, the effective
holdout_test (post guard-mutation), reward, exit_code, total_tests, and the
call logs of every stubbed boundary (run_tool, write_progress,
compute_reward, registry.execute, prompt_guard.check, grade_against_holdout).

Usage:
    python scripts/shadow_runner.py --selftest [--max-scenarios N]

Exit code 0 iff every scenario matches. Importable as
`from scripts.shadow_runner import run_selftest, run_verify_selftest` (used
by tests/test_loop_runner.py and tests/test_loop_verify.py); heavy work is
guarded under __main__.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.pipeline as cp  # noqa: E402
import core.loop.handlers.finalize as fz  # noqa: E402
import core.loop.handlers.verify as vf  # noqa: E402
import core.holdout as ho  # noqa: E402
import core.prompt_guard as pg  # noqa: E402
import gems.grandidierite.registry as gr  # noqa: E402
from core.loop.handlers.finalize import FinalizeContext  # noqa: E402
from core.loop.handlers.verify import VerificationContext  # noqa: E402
from core.loop.runner import LoopRunner  # noqa: E402
from core.pipeline import Pipeline, PipelineResult, StageResult  # noqa: E402
from core.schemas import (  # noqa: E402
    BlackTourmalineResponse,
    ClearQuartzResponse,
    LabradoriteResponse,
    PolicyViolation,
)

# Keys excluded from every comparison: observability-only, never semantic.
VOLATILE_KEYS = ("duration_ms", "finished_at", "task_id")


@dataclass
class Scenario:
    name: str
    objective: str = "write f"
    generated: str = "def f():\n    return 1\n"
    exit_code: Optional[int] = 0
    has_sandbox: bool = True
    last_err: str = ""
    fail_kind: str = ""
    strategy: str = "default"
    confidence: float = 0.9
    verification_score: float = 1.0
    total_tests: int = 2
    holdout_ok: Optional[bool] = True
    holdout_test: str = ""
    tool_assist: bool = True
    result_error: Optional[str] = None
    # boundary behaviours
    frozen: bool = False
    proposal: Optional[Dict[str, Any]] = None
    exp_raises: bool = False
    run_tool_raises: bool = False
    cit_result: Dict[str, Any] = field(default_factory=lambda: {"ok": True})


def _scenarios() -> List[Scenario]:
    return [
        Scenario(name="success_exit0_tool_assist"),
        Scenario(
            name="failure_exit1_fabricate_proposal",
            exit_code=1,
            last_err="AssertionError: boom",
            fail_kind="assertion",
            confidence=0.1,
            verification_score=0.0,
            holdout_ok=False,
            proposal={"name": "assertion_helper", "action": "fabricate"},
        ),
        Scenario(
            name="failure_bench_frozen",
            exit_code=1,
            last_err="SyntaxError: bad",
            fail_kind="syntax",
            confidence=0.0,
            verification_score=0.0,
            holdout_ok=False,
            proposal={"name": "syntax_fixer", "action": "fabricate"},
            frozen=True,
        ),
        Scenario(name="success_tool_assist_off", tool_assist=False),
        Scenario(name="experience_record_raises", exp_raises=True),
        Scenario(
            name="citrine_down",
            cit_result={"ok": False, "error": "citrine down"},
        ),
        Scenario(
            name="failure_error_already_set",
            exit_code=1,
            last_err="stderr text",
            fail_kind="runtime",
            confidence=0.2,
            verification_score=0.0,
            result_error="code failed",
        ),
        Scenario(name="memory_save_outer_raise", run_tool_raises=True),
        Scenario(name="no_sandbox_failure", exit_code=None, has_sandbox=False),
    ]


class _StubFactory:
    """Builds identical boundary stubs for one path, logging every call."""

    def __init__(self, sc: Scenario, log: List[Any]):
        self.sc = sc
        self.log = log

    @staticmethod
    def _kwargs(kwargs: Dict[str, Any]) -> str:
        return json.dumps(kwargs, sort_keys=True, default=str)

    def record_outcome(self, success: bool, error: Optional[str] = None) -> None:
        self.log.append(("record_outcome", success, error))

    def experience_record(self, **kwargs: Any) -> None:
        self.log.append(("experience_record", self._kwargs(kwargs)))
        if self.sc.exp_raises:
            raise RuntimeError("experience store exploded")

    def maybe_propose_fabricate(self) -> Optional[Dict[str, Any]]:
        self.log.append(("maybe_propose_fabricate",))
        return self.sc.proposal

    def is_frozen(self) -> bool:
        self.log.append(("is_frozen",))
        return self.sc.frozen

    def run_tool(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.log.append(("run_tool", name, self._kwargs(payload)))
        if self.sc.run_tool_raises:
            raise RuntimeError("tool runner exploded")
        return {"ok": True}

    def index_pass_pattern(self, **kwargs: Any) -> Dict[str, Any]:
        self.log.append(("index_pass_pattern", self._kwargs(kwargs)))
        return self.sc.cit_result

    def registry(self) -> Any:
        log = self.log

        class _FakeRegistry:
            degraded: List[str] = []

            def execute(self, request: Any) -> Any:
                payload = getattr(request, "payload", None)
                summary = self._payload_summary(payload)
                log.append(("registry.execute", request.target_gem, summary))

                class _Res:
                    error = None

                return _Res()

            @staticmethod
            def _payload_summary(payload: Any) -> str:
                tr = getattr(payload, "tool_request", None)
                return json.dumps(tr, sort_keys=True, default=str)

        return _FakeRegistry()


def _fresh_result(sc: Scenario, task_id: UUID) -> PipelineResult:
    result = PipelineResult(task_id=task_id, objective=sc.objective)
    result.confidence = sc.confidence
    result.verification_score = sc.verification_score
    result.holdout_ok = sc.holdout_ok
    result.error = sc.result_error
    result.status = "complete"  # PipelineResult default at tail entry
    if sc.has_sandbox:
        result.sandbox = ClearQuartzResponse(
            exit_code=sc.exit_code or 0,
            total_tests=sc.total_tests,
            tests_passed=sc.total_tests if sc.exit_code == 0 else 0,
        )
    return result


def _install(module: Any, names: Dict[str, Callable[..., Any]]) -> Dict[str, Any]:
    saved = {n: getattr(module, n) for n in names}
    for n, fn in names.items():
        setattr(module, n, fn)
    return saved


def _restore(module: Any, saved: Dict[str, Any]) -> None:
    for n, fn in saved.items():
        setattr(module, n, fn)


def _run_legacy(sc: Scenario, task_id: UUID, log: List[Any]) -> PipelineResult:
    stubs = _StubFactory(sc, log)
    result = _fresh_result(sc, task_id)
    pipe = object.__new__(Pipeline)  # no __init__ side effects; tail needs only .registry
    pipe.registry = stubs.registry()
    saved_cp = _install(
        cp,
        {
            "record_outcome": stubs.record_outcome,
            "experience_record": stubs.experience_record,
            "maybe_propose_fabricate": stubs.maybe_propose_fabricate,
            "is_frozen": stubs.is_frozen,
            "index_pass_pattern": stubs.index_pass_pattern,
        },
    )
    saved_gr = _install(gr, {"run_tool": stubs.run_tool})
    try:
        pipe._finalize_legacy(
            result,
            objective=sc.objective,
            generated=sc.generated,
            last_err=sc.last_err,
            fail_kind=sc.fail_kind,
            strategy=sc.strategy,
            total_tests=sc.total_tests,
            holdout_test=sc.holdout_test,
            tool_assist=sc.tool_assist,
            exit_code=sc.exit_code,
        )
    finally:
        _restore(cp, saved_cp)
        _restore(gr, saved_gr)
    return result


def _run_new(sc: Scenario, task_id: UUID, log: List[Any]) -> PipelineResult:
    stubs = _StubFactory(sc, log)
    result = _fresh_result(sc, task_id)
    saved_fz = _install(
        fz,
        {
            "record_outcome": stubs.record_outcome,
            "experience_record": stubs.experience_record,
            "maybe_propose_fabricate": stubs.maybe_propose_fabricate,
            "is_frozen": stubs.is_frozen,
            "index_pass_pattern": stubs.index_pass_pattern,
        },
    )
    try:
        outcome = LoopRunner(registry=stubs.registry(), run_tool=stubs.run_tool).run_finalize(
            FinalizeContext(
                task_id=str(task_id),
                objective=sc.objective,
                generated=sc.generated or "",
                success=(sc.exit_code == 0),
                last_err=sc.last_err,
                fail_kind=sc.fail_kind,
                strategy=sc.strategy,
                confidence=result.confidence,
                verification_score=result.verification_score,
                total_tests=sc.total_tests,
                holdout_ok=result.holdout_ok,
                holdout_test=sc.holdout_test,
                tool_assist=sc.tool_assist,
                has_sandbox=result.sandbox is not None,
                exit_code=sc.exit_code,
                result_error=result.error,
            )
        )
        # Exactly the application block from Pipeline.run's flag branch.
        for _s in outcome.stages:
            result.stages.append(StageResult(**_s))
        result.degraded.extend(outcome.degraded)
        result.status = outcome.status
        if outcome.error is not None:
            result.error = outcome.error
    finally:
        _restore(fz, saved_fz)
    return result


def _observable(result: PipelineResult, log: List[Any]) -> Dict[str, Any]:
    return {
        "stages": [
            {k: v for k, v in s.model_dump().items() if k not in VOLATILE_KEYS}
            for s in result.stages
        ],
        "status": result.status,
        "error": result.error,
        "degraded": list(result.degraded),
        "side_effects": list(log),
    }


def _diff_scenario(tag: str, name: str, legacy: Dict[str, Any], new: Dict[str, Any]) -> bool:
    if legacy == new:
        print(f"PASS {name}")
        return True
    print(f"FAIL {name}")
    old = json.dumps(legacy, indent=2, sort_keys=True, default=str).splitlines()
    new_lines = json.dumps(new, indent=2, sort_keys=True, default=str).splitlines()
    for line in difflib.unified_diff(old, new_lines, fromfile="legacy", tofile=tag, lineterm=""):
        print(line)
    return False


# -- verification-spine scenarios (stage 2) -----------------------------------


@dataclass
class VerifyScenario:
    name: str
    objective: str = "write f"
    generated: str = "def f():\n    return 1\n"
    tool_assist: bool = True
    critique: bool = False
    holdout_test: str = ""
    sent_prompts: List[str] = field(default_factory=lambda: ["Write Python code for:\nwrite f"])
    has_sandbox: bool = True
    sandbox_exit: Optional[int] = 0
    sandbox_total_tests: int = 2
    confidence: float = 0.9
    verification_score: float = 1.0
    retries: int = 0
    plan_ok: bool = True
    first_compile_ok: bool = True
    used_burst: bool = False
    # boundary behaviours
    scan: Dict[str, Any] = field(default_factory=lambda: {"ok": True, "result": {"clean": True}})
    sub: Dict[str, Any] = field(default_factory=lambda: {"ok": True, "result": {"risky": False}})
    run_tool_raises: bool = False
    audit_payload: Optional[Any] = field(
        default_factory=lambda: BlackTourmalineResponse(approved=True, risk_score=0.1)
    )
    audit_error: Optional[str] = None
    crit_payload: Optional[Any] = field(
        default_factory=lambda: LabradoriteResponse(critique="solid, minor naming issues")
    )
    crit_error: Optional[str] = None
    guard: Dict[str, Any] = field(
        default_factory=lambda: {"clean": True, "leak_count": 0, "detail": ""}
    )
    guard_raises: bool = False
    grade: Dict[str, Any] = field(default_factory=lambda: {"ok": True, "asserts": 2})
    grade_raises: bool = False


def _verify_scenarios() -> List[VerifyScenario]:
    return [
        VerifyScenario(name="audit_approved"),
        VerifyScenario(
            name="audit_rejected_violations",
            audit_payload=BlackTourmalineResponse(
                approved=False,
                violations=[PolicyViolation(rule="no-eval", severity="high", message="eval used")],
                risk_score=0.7,
            ),
        ),
        VerifyScenario(
            name="audit_gem_outage",
            audit_error="black-tourmaline unreachable",
        ),
        VerifyScenario(name="critique_on_success", critique=True),
        VerifyScenario(
            name="critique_on_outage",
            critique=True,
            crit_error="labradorite down",
        ),
        VerifyScenario(
            name="tool_scan_risky_exec",
            sub={"ok": True, "result": {"risky": True}},
        ),
        VerifyScenario(
            name="tool_scan_secrets_dirty",
            scan={"ok": True, "result": {"clean": False}},
        ),
        VerifyScenario(name="tool_scan_runner_raises", run_tool_raises=True),
        VerifyScenario(
            name="holdout_pass",
            holdout_test="assert f() == 1",
        ),
        VerifyScenario(
            name="holdout_fail",
            holdout_test="assert f() == 2",
            grade={"ok": False, "asserts": 1, "reason": "assertion failed"},
        ),
        VerifyScenario(
            name="holdout_leak_guard_not_clean",
            holdout_test="assert f() == 1",
            guard={"clean": False, "leak_count": 1, "detail": "holdout fragment #1 in prompt"},
        ),
        VerifyScenario(
            name="guard_raises_fail_open",
            holdout_test="assert f() == 1",
            guard_raises=True,
        ),
        VerifyScenario(
            name="grade_raises_fails_closed",
            holdout_test="assert f() == 1",
            grade_raises=True,
        ),
        VerifyScenario(
            name="no_sandbox_tool_assist_off",
            tool_assist=False,
            has_sandbox=False,
            sandbox_exit=None,
            sandbox_total_tests=0,
            confidence=0.0,
            verification_score=0.0,
            plan_ok=False,
            first_compile_ok=False,
        ),
    ]


class _VerifyStubs:
    """Identical spine boundary stubs for one path, logging every call."""

    def __init__(self, sc: VerifyScenario, log: List[Any]):
        self.sc = sc
        self.log = log

    @staticmethod
    def _kwargs(kwargs: Dict[str, Any]) -> str:
        return json.dumps(kwargs, sort_keys=True, default=str)

    def run_tool(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.log.append(("run_tool", name, self._kwargs(payload)))
        if self.sc.run_tool_raises:
            raise RuntimeError("tool runner exploded")
        return {"secret_scan": self.sc.scan, "subprocess_audit": self.sc.sub}.get(
            name, {"ok": True}
        )

    def write_progress(self, tid: str, objective: str, stage: str, *a: Any) -> None:
        self.log.append(("write_progress", tid, objective, stage))

    def compute_reward(self, **kwargs: Any) -> float:
        # Deterministic constant: equality of the logged kwargs is the proof.
        self.log.append(("compute_reward", self._kwargs(kwargs)))
        return 0.42

    def guard_check(self, prompt: str, holdout_test: str) -> Dict[str, Any]:
        self.log.append(
            ("prompt_guard.check", self._kwargs({"prompt": prompt, "holdout": holdout_test}))
        )
        if self.sc.guard_raises:
            raise RuntimeError("guard exploded")
        return self.sc.guard

    def grade(self, code: str, hidden_test: str) -> Dict[str, Any]:
        self.log.append(
            ("grade_against_holdout", self._kwargs({"code": code, "hidden_test": hidden_test}))
        )
        if self.sc.grade_raises:
            raise RuntimeError("grading exploded")
        return self.sc.grade

    def registry(self) -> Any:
        sc = self.sc
        log = self.log

        class _Err:
            def __init__(self, message: str):
                self.message = message

        class _Res:
            def __init__(self, error: Any = None, payload: Any = None):
                self.error = error
                self.payload = payload

        class _FakeRegistry:
            degraded: List[str] = []

            def execute(self, request: Any) -> Any:
                log.append(("registry.execute", request.target_gem))
                if request.target_gem == "black-tourmaline":
                    if sc.audit_error is not None:
                        return _Res(error=_Err(sc.audit_error))
                    return _Res(payload=sc.audit_payload)
                if request.target_gem == "labradorite":
                    if sc.crit_error is not None:
                        return _Res(error=_Err(sc.crit_error))
                    return _Res(payload=sc.crit_payload)
                return _Res()

        return _FakeRegistry()


def _verify_fresh_result(sc: VerifyScenario, task_id: UUID) -> PipelineResult:
    result = PipelineResult(task_id=task_id, objective=sc.objective)
    result.confidence = sc.confidence
    result.verification_score = sc.verification_score
    result.retries = sc.retries
    result.plan_ok = sc.plan_ok
    result.first_compile_ok = sc.first_compile_ok
    result.used_burst = sc.used_burst
    result.generated_code = sc.generated
    if sc.has_sandbox:
        result.sandbox = ClearQuartzResponse(
            exit_code=sc.sandbox_exit or 0,
            total_tests=sc.sandbox_total_tests,
            tests_passed=sc.sandbox_total_tests if sc.sandbox_exit == 0 else 0,
        )
    return result


def _guard_stubs(stubs: "_VerifyStubs") -> Dict[str, Any]:
    return {
        "pg": (pg, {"check": stubs.guard_check}),
        "ho": (ho, {"grade_against_holdout": stubs.grade}),
    }


def _run_verify_legacy(
    sc: VerifyScenario, task_id: UUID, log: List[Any]
) -> "tuple[PipelineResult, Optional[int], int, str]":
    stubs = _VerifyStubs(sc, log)
    result = _verify_fresh_result(sc, task_id)
    pipe = object.__new__(Pipeline)  # no __init__ side effects; spine needs only .registry
    pipe.registry = stubs.registry()
    saved_cp = _install(
        cp, {"write_progress": stubs.write_progress, "compute_reward": stubs.compute_reward}
    )
    saved_gr = _install(gr, {"run_tool": stubs.run_tool})
    guard_mods = _guard_stubs(stubs)
    saved_guard = {k: _install(m, names) for k, (m, names) in guard_mods.items()}
    try:
        ec, tt, ht = pipe._verify_legacy(
            result,
            objective=sc.objective,
            generated=sc.generated,
            critique=sc.critique,
            holdout_test=sc.holdout_test,
            sent_prompts=list(sc.sent_prompts),
            tool_assist=sc.tool_assist,
        )
    finally:
        _restore(cp, saved_cp)
        _restore(gr, saved_gr)
        for k, (m, _names) in guard_mods.items():
            _restore(m, saved_guard[k])
    return result, ec, tt, ht


def _run_verify_new(
    sc: VerifyScenario, task_id: UUID, log: List[Any]
) -> "tuple[PipelineResult, Optional[int], int, str]":
    stubs = _VerifyStubs(sc, log)
    result = _verify_fresh_result(sc, task_id)
    saved_vf = _install(
        vf, {"write_progress": stubs.write_progress, "compute_reward": stubs.compute_reward}
    )
    guard_mods = _guard_stubs(stubs)
    saved_guard = {k: _install(m, names) for k, (m, names) in guard_mods.items()}
    try:
        outcome = LoopRunner(registry=stubs.registry(), run_tool=stubs.run_tool).run_verify(
            VerificationContext(
                task_id=str(task_id),
                objective=sc.objective,
                generated=sc.generated or "",
                tool_assist=sc.tool_assist,
                critique=sc.critique,
                holdout_test=sc.holdout_test,
                sent_prompts=list(sc.sent_prompts),
                has_sandbox=result.sandbox is not None,
                sandbox_exit=result.sandbox.exit_code if result.sandbox else None,
                sandbox_total_tests=int(result.sandbox.total_tests) if result.sandbox else 0,
                confidence=result.confidence,
                verification_score=result.verification_score,
                retries=result.retries,
                plan_ok=result.plan_ok,
                first_compile_ok=result.first_compile_ok,
                used_burst=result.used_burst,
            )
        )
        # Exactly the application block from Pipeline.run's flag branch.
        for _s in outcome.stages:
            result.stages.append(StageResult(**_s))
        result.confidence = outcome.confidence
        if outcome.audit is not None:
            result.audit = BlackTourmalineResponse.model_validate(outcome.audit)
        if outcome.critique is not None:
            result.critique = LabradoriteResponse.model_validate(outcome.critique)
        result.holdout_ok = outcome.holdout_ok
        result.reward = outcome.reward
        ec, tt, ht = outcome.exit_code, outcome.total_tests, outcome.holdout_test
    finally:
        _restore(vf, saved_vf)
        for k, (m, _names) in guard_mods.items():
            _restore(m, saved_guard[k])
    return result, ec, tt, ht


def _verify_observable(
    result: PipelineResult, ec: Optional[int], tt: int, ht: str, log: List[Any]
) -> Dict[str, Any]:
    return {
        "stages": [
            {k: v for k, v in s.model_dump().items() if k not in VOLATILE_KEYS}
            for s in result.stages
        ],
        "confidence": result.confidence,
        "audit": result.audit.model_dump(mode="json") if result.audit is not None else None,
        "critique": (
            result.critique.model_dump(mode="json") if result.critique is not None else None
        ),
        "holdout_ok": result.holdout_ok,
        "holdout_test": ht,
        "reward": result.reward,
        "exit_code": ec,
        "total_tests": tt,
        "side_effects": list(log),
    }


def run_verify_selftest(max_scenarios: Optional[int] = None) -> bool:
    """Run every spine scenario through both paths and diff. True iff equal."""
    scenarios = _verify_scenarios()
    if max_scenarios is not None:
        scenarios = scenarios[:max_scenarios]
    all_ok = True
    for sc in scenarios:
        task_id = uuid4()
        legacy_log: List[Any] = []
        new_log: List[Any] = []
        legacy = _verify_observable(*_run_verify_legacy(sc, task_id, legacy_log), legacy_log)
        new = _verify_observable(*_run_verify_new(sc, task_id, new_log), new_log)
        all_ok = _diff_scenario("loop_runner", sc.name, legacy, new) and all_ok
    print(f"verify shadow selftest: {'PASS' if all_ok else 'FAIL'} ({len(scenarios)} scenarios)")
    return all_ok


def run_selftest(max_scenarios: Optional[int] = None) -> bool:
    """Run every finalize + verify scenario through both paths. True iff equal."""
    scenarios = _scenarios()
    if max_scenarios is not None:
        scenarios = scenarios[:max_scenarios]
    all_ok = True
    for sc in scenarios:
        task_id = uuid4()
        legacy_log: List[Any] = []
        new_log: List[Any] = []
        legacy = _observable(_run_legacy(sc, task_id, legacy_log), legacy_log)
        new = _observable(_run_new(sc, task_id, new_log), new_log)
        all_ok = _diff_scenario("loop_runner", sc.name, legacy, new) and all_ok
    print(f"finalize shadow selftest: {'PASS' if all_ok else 'FAIL'} ({len(scenarios)} scenarios)")
    verify_ok = run_verify_selftest(max_scenarios=max_scenarios)
    return all_ok and verify_ok


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run the synthetic finalize scenarios through both paths and diff",
    )
    parser.add_argument(
        "--max-scenarios",
        type=int,
        default=None,
        metavar="N",
        help="cap the scenario count (CI smoke)",
    )
    args = parser.parse_args(argv)
    if not args.selftest:
        parser.print_help()
        return 2
    return 0 if run_selftest(max_scenarios=args.max_scenarios) else 1


if __name__ == "__main__":
    raise SystemExit(main())
