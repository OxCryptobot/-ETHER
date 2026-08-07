"""Training doctrine unit tests — no LLM."""
from __future__ import annotations

from pathlib import Path

from core.train_gates import (
    classify_fail_kind,
    may_record_fail,
    may_record_pass,
    strategy_boost,
)
from core import experience


def test_may_record_pass_requires_verification():
    ok, reason = may_record_pass(
        success=True, verification_score=0.5, total_tests=3, holdout_ok=None
    )
    assert ok is False
    assert "verification" in reason or "unverified" in reason


def test_may_record_pass_holdout_ok():
    ok, reason = may_record_pass(
        success=True, verification_score=0.0, total_tests=0, holdout_ok=True
    )
    assert ok is True
    assert reason == "holdout_ok"


def test_may_record_pass_full_score():
    ok, reason = may_record_pass(
        success=True, verification_score=1.0, total_tests=4, holdout_ok=None
    )
    assert ok is True


def test_may_record_fail_skips_infra():
    ok, reason = may_record_fail(
        success=False, stderr="cannot connect to ollama", fail_kind="runtime"
    )
    assert ok is False


def test_may_record_fail_code():
    ok, reason = may_record_fail(
        success=False, stderr="AssertionError: expected 3", fail_kind="AssertionError"
    )
    assert ok is True


def test_strategy_boost_prefers_tool_runtime():
    assert strategy_boost("tool_runtime") > strategy_boost("best_of_n")
    assert strategy_boost("tool_runtime") > strategy_boost("agent_loop")


def test_classify_fail_kind():
    assert classify_fail_kind("SyntaxError: invalid") == "SyntaxError"
    assert classify_fail_kind("docker daemon") == "infra"


def test_experience_record_rejects_unverified(tmp_path, monkeypatch):
    monkeypatch.setattr(experience, "VAULT_DIR", tmp_path)
    monkeypatch.setattr(experience, "PASS_PATH", tmp_path / "pass.jsonl")
    monkeypatch.setattr(experience, "FAIL_PATH", tmp_path / "fail.jsonl")
    meta = experience.record(
        objective="add two numbers",
        code="def add(a,b): return a+b",
        success=True,
        verification_score=0.0,
        total_tests=0,
        holdout_ok=None,
    )
    assert meta["stored"] is False
    assert not (tmp_path / "pass.jsonl").exists()


def test_experience_record_accepts_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(experience, "VAULT_DIR", tmp_path)
    monkeypatch.setattr(experience, "PASS_PATH", tmp_path / "pass.jsonl")
    monkeypatch.setattr(experience, "FAIL_PATH", tmp_path / "fail.jsonl")
    meta = experience.record(
        objective="add two numbers",
        code="def add(a,b): return a+b",
        success=True,
        verification_score=1.0,
        total_tests=2,
        strategy="tool_runtime",
        holdout_ok=True,
    )
    assert meta["stored"] is True
    assert (tmp_path / "pass.jsonl").exists()
