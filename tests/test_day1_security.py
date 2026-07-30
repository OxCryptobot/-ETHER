"""Day-1 security fail-closed (B1/S-01, B2/S-03).

Pins the two roadmap Day-1 changes: the local sandbox fallback is visible on
every success path (without tanking the static-analysis score), and the
push-to-exec command channel of the tracked batch queue is closed unless an
operator explicitly opts in with ETHER_BATCH_COMMANDS=1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

import core.batch_queue as bq
from core.confidence import compute_scores
from core.schemas import ClearQuartzRequest, ClearQuartzResponse, Envelope, GemErrorType
from gems.clear_quartz.sandbox import ClearQuartz
from scripts.batch_worker import process_one

ROOT = Path(__file__).resolve().parents[1]


def _execute(code: str = "print(1)"):
    return ClearQuartz().execute(
        Envelope(
            task_id=uuid4(),
            target_gem="clear-quartz",
            payload=ClearQuartzRequest(code=code, objective=""),
            timeout_seconds=30,
        )
    )


def _isolated_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(bq, "QUEUE_PATH", tmp_path / "batch_queue.json")
    monkeypatch.setattr(bq, "HIST_PATH", tmp_path / "bq" / "history.jsonl")
    monkeypatch.setattr(bq, "LOCK_PATH", tmp_path / "bq" / ".queue.lock")
    return bq


# --------------------------------------------------------------------------
# B1/S-01 — sandbox fallback visibility
# --------------------------------------------------------------------------


def test_explicit_local_backend_emits_fallback_flag(monkeypatch):
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "local")

    res = _execute()

    assert res.error is None
    assert res.payload is not None
    assert res.payload.exit_code == 0
    assert "sandbox_fallback:local" in res.payload.security_flags
    # Benign code: the visibility marker is not a static-analysis finding and
    # must not tank the score.
    assert res.payload.static_analysis_score == 1.0


def test_auto_backend_without_docker_emits_flag(monkeypatch):
    monkeypatch.delenv("ETHER_SANDBOX_BACKEND", raising=False)
    monkeypatch.setattr("gems.clear_quartz.sandbox.shutil.which", lambda _name: None)

    res = _execute()

    assert res.error is None
    assert res.payload is not None
    assert res.payload.exit_code == 0
    assert "sandbox_fallback:local" in res.payload.security_flags
    assert res.payload.static_analysis_score == 1.0


def test_explicit_docker_fails_closed_without_docker(monkeypatch):
    """Explicit docker is a security decision: no silent host re-run."""
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "docker")
    monkeypatch.setattr("gems.clear_quartz.sandbox.shutil.which", lambda _name: None)

    res = _execute()

    assert res.payload is None
    assert res.error is not None
    assert res.error.type == GemErrorType.DEPENDENCY
    assert "Docker" in res.error.message
    # Nothing executed on the host: no fallback marker anywhere.
    assert "sandbox_fallback" not in str(res)


def test_fallback_marker_does_not_tank_confidence():
    """FIX-1: the marker is visibility-only — scoring treats it as a non-event.

    A local-backend run carries ONLY the visibility marker; it must score
    exactly like a flag-free run so the flywheel gate keeps functioning on
    dockerless hosts. Real static findings must still be penalized exactly
    as before.
    """
    base = dict(
        exit_code=0,
        total_tests=5,
        tests_passed=5,
        static_analysis_score=1.0,
        execution_time=1.0,
    )
    flag_free = compute_scores(ClearQuartzResponse(**base))
    marker_only = compute_scores(
        ClearQuartzResponse(**base, security_flags=["sandbox_fallback:local"])
    )
    assert marker_only == flag_free

    penalized = compute_scores(
        ClearQuartzResponse(**base, security_flags=["dangerous_attr:system"])
    )
    assert penalized["execution_score"] == 0.25
    assert penalized["verification_score"] == 0.25
    assert penalized["confidence"] == 0.25
    assert penalized != flag_free

    # A real finding alongside the marker is still penalized: only the
    # marker is stripped, the finding is not.
    mixed = compute_scores(
        ClearQuartzResponse(
            **base,
            security_flags=["sandbox_fallback:local", "dangerous_attr:system"],
        )
    )
    assert mixed == penalized


# --------------------------------------------------------------------------
# B2/S-03 — command channel closed at enqueue and at execution
# --------------------------------------------------------------------------


def test_enqueue_command_refused_by_default(tmp_path, monkeypatch):
    queue = _isolated_queue(tmp_path, monkeypatch)
    monkeypatch.delenv("ETHER_BATCH_COMMANDS", raising=False)

    with pytest.raises(ValueError, match="command queue items are disabled"):
        queue.enqueue(kind="command", title="t", command=["echo", "hi"])

    assert queue.load_queue()["pending"] == []


def test_enqueue_command_allowed_with_env(tmp_path, monkeypatch):
    queue = _isolated_queue(tmp_path, monkeypatch)
    monkeypatch.setenv("ETHER_BATCH_COMMANDS", "1")

    item = queue.enqueue(kind="command", title="t", command=["echo", "hi"])

    assert item["kind"] == "command"
    assert item["command"] == ["echo", "hi"]
    pending = queue.load_queue()["pending"]
    assert [p["id"] for p in pending] == [item["id"]]


def test_batch_worker_command_refused_by_default(monkeypatch):
    monkeypatch.delenv("ETHER_BATCH_COMMANDS", raising=False)

    result = process_one({"kind": "command", "command": ["python", "-c", "pass"], "title": "t"})

    assert result["ok"] is False
    assert "disabled (S-03)" in result["error"]
    assert "returncode" not in result, "the command ran despite the refusal"


def test_batch_worker_command_executes_with_env(monkeypatch):
    monkeypatch.setenv("ETHER_BATCH_COMMANDS", "1")

    result = process_one({"kind": "command", "command": ["python", "-c", "pass"], "title": "t"})

    assert result["ok"] is True
    assert result["returncode"] == 0
    assert result["command"][0] == sys.executable


# --------------------------------------------------------------------------
# Tracked state — the push vector itself must be clean
# --------------------------------------------------------------------------


def test_tracked_queue_has_no_command_items():
    data = json.loads((ROOT / "memory" / "batch_queue.json").read_text(encoding="utf-8"))
    pending_commands = [i for i in data.get("pending", []) if i.get("kind") == "command"]
    assert pending_commands == [], f"tracked queue still carries command items: {pending_commands}"


def test_service_file_not_backend_local():
    content = (ROOT / "deploy" / "ether.service").read_text(encoding="utf-8")
    assert "ETHER_SANDBOX_BACKEND=local" not in content
    assert "ETHER_SANDBOX_BACKEND=docker" in content
