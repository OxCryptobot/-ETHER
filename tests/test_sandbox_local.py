"""Local sandbox backend (no Docker)."""

from __future__ import annotations

import os
from uuid import uuid4

from core.schemas import Envelope, ClearQuartzRequest
from gems.clear_quartz.sandbox import ClearQuartz, sandbox_backend


def test_sandbox_backend_local(monkeypatch):
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "local")
    assert sandbox_backend() == "local"


def test_local_runs_python(monkeypatch):
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "local")
    gem = ClearQuartz()
    res = gem.execute(
        Envelope(
            task_id=uuid4(),
            target_gem="clear-quartz",
            # The assertion must depend on the code under test. This used to
            # read `assert 2+2==4`, a constant that cannot fail and proves
            # nothing — exactly the pattern that let no-op artifacts score a
            # perfect verification. See tests/test_assert_audit.py.
            payload=ClearQuartzRequest(
                code="def add(a, b):\n    return a + b\nprint(add(2, 2))\nassert add(2, 2) == 4\n"
            ),
            timeout_seconds=30,
        )
    )
    assert res.error is None
    assert res.payload is not None
    assert res.payload.exit_code == 0
    assert "4" in (res.payload.stdout or "")
    assert res.payload.total_tests >= 1


def test_local_does_not_count_constant_asserts(monkeypatch):
    """A constant assertion is not evidence about the generated code."""
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "local")
    res = ClearQuartz().execute(
        Envelope(
            task_id=uuid4(),
            target_gem="clear-quartz",
            payload=ClearQuartzRequest(code="print(2+2)\nassert 2+2==4\n"),
            timeout_seconds=30,
        )
    )
    assert res.payload is not None
    assert res.payload.exit_code == 0
    assert res.payload.total_tests == 0
