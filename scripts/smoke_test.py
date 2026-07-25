#!/usr/bin/env python3
"""Smoke test that does not require Docker or Ollama."""

from core.schemas import ClearQuartzResponse, Envelope, ClearQuartzRequest
from core.orchestrator import Orchestrator, Status
from core.confidence import compute_clear_quartz_confidence
from uuid import uuid4


def main() -> None:
    # schemas
    r = ClearQuartzResponse(exit_code=0, total_tests=2, tests_passed=2)
    assert compute_clear_quartz_confidence(r) > 0.5

    # orchestrator happy path
    orch = Orchestrator()
    tid = uuid4()
    orch.start(tid)
    req = Envelope(task_id=tid, target_gem="clear-quartz", payload=ClearQuartzRequest(code="print(1)"))
    from core.schemas import ResponseEnvelope

    def ok():
        return ResponseEnvelope(task_id=tid, source_gem="clear-quartz", payload=ClearQuartzResponse(exit_code=0))

    assert orch.process_response(req, ok()) == Status.EXECUTING
    assert orch.process_response(req, ok()) == Status.VALIDATING
    assert orch.process_response(req, ok()) == Status.AUDITING
    assert orch.process_response(req, ok()) == Status.COMPLETE
    print("SMOKE OK")


if __name__ == "__main__":
    main()
