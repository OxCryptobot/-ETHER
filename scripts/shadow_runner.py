"""Stage-level shadow differ for the strangler-fig migration.

Runs synthetic finalize scenarios through BOTH finalize paths — the legacy
inline tail (`Pipeline._finalize_legacy`) and the extracted
`LoopRunner.run_finalize` — against identical stubbed boundaries, and diffs
the observable result: stages (excluding duration_ms), status, error,
degraded, plus the side-effect call logs of every stubbed boundary.

Usage:
    python scripts/shadow_runner.py --selftest [--max-scenarios N]

Exit code 0 iff every scenario matches. Importable as
`from scripts.shadow_runner import run_selftest` (used by
tests/test_loop_runner.py); heavy work is guarded under __main__.
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
import gems.grandidierite.registry as gr  # noqa: E402
from core.loop.handlers.finalize import FinalizeContext  # noqa: E402
from core.loop.runner import LoopRunner  # noqa: E402
from core.pipeline import Pipeline, PipelineResult, StageResult  # noqa: E402
from core.schemas import ClearQuartzResponse  # noqa: E402

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


def run_selftest(max_scenarios: Optional[int] = None) -> bool:
    """Run every scenario through both paths and diff. Returns True iff equal."""
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
        if legacy == new:
            print(f"PASS {sc.name}")
        else:
            all_ok = False
            print(f"FAIL {sc.name}")
            old = json.dumps(legacy, indent=2, sort_keys=True, default=str).splitlines()
            new_lines = json.dumps(new, indent=2, sort_keys=True, default=str).splitlines()
            for line in difflib.unified_diff(
                old, new_lines, fromfile="legacy", tofile="loop_runner", lineterm=""
            ):
                print(line)
    print(f"shadow selftest: {'PASS' if all_ok else 'FAIL'} ({len(scenarios)} scenarios)")
    return all_ok


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
