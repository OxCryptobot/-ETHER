"""Tests for the Control Matrix integrity panels.

These surface state the dashboard previously had no representation for: how
much output was actually verified, whether the sandbox is really isolated, and
whether the memory layer is alive. A dead memory layer used to be invisible on
every surface at once.
"""

from __future__ import annotations

import pytest

from dashboard.collector import (
    _memory_block,
    _posture_block,
    _sandbox_info,
    _verification_block,
)


def test_posture_reports_all_risk_switches(monkeypatch):
    for var in (
        "ETHER_PATCH_LOOP",
        "ETHER_AUTO_PROMOTE",
        "ETHER_FLYWHEEL_PUSH",
        "ETHER_GIT_RESET_OK",
        "ETHER_BURST",
    ):
        monkeypatch.setenv(var, "1")
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "local")
    posture = _posture_block()
    assert posture["patch_loop"] is True
    assert posture["auto_promote"] is True
    assert posture["flywheel_push"] is True
    assert posture["git_reset_ok"] is True
    assert posture["burst"] is True
    # Every enabled switch must be called out, including host execution.
    assert len(posture["risk_notes"]) == 6


def test_posture_is_quiet_when_everything_is_off(monkeypatch):
    for var in (
        "ETHER_PATCH_LOOP",
        "ETHER_AUTO_PROMOTE",
        "ETHER_FLYWHEEL_PUSH",
        "ETHER_GIT_RESET_OK",
        "ETHER_BURST",
    ):
        monkeypatch.setenv(var, "0")
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "docker")
    posture = _posture_block()
    assert posture["risk_notes"] == []


def test_docker_backend_does_not_claim_a_local_fallback(monkeypatch):
    """The docker backend fails closed; reporting a fallback would be a lie."""
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "docker")
    monkeypatch.setattr("dashboard.collector.shutil.which", lambda _n: None)
    info = _sandbox_info()
    assert info["isolated"] is False
    assert "fails closed" in info["effective"]
    assert "fallback" not in info["effective"]


def test_docker_backend_reports_isolated_when_available(monkeypatch):
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "docker")
    monkeypatch.setattr("dashboard.collector.shutil.which", lambda _n: "/usr/bin/docker")
    info = _sandbox_info()
    assert info["isolated"] is True
    assert info["effective"] == "docker"


def test_verification_block_has_required_keys():
    v = _verification_block()
    for key in (
        "runs_sampled",
        "runs_with_real_tests",
        "runs_untested",
        "verified_fraction",
        "holdout_dataset",
        "holdout_wired_to_gate",
    ):
        assert key in v
    assert v["runs_sampled"] == v["runs_with_real_tests"] + v["runs_untested"]


def test_holdout_wiring_reflects_curriculum_coverage():
    """The flag must track real coverage, not be hardcoded either way."""
    v = _verification_block()
    assert v["curriculum_tasks"] > 0
    expected = v["curriculum_with_holdout"] == v["curriculum_tasks"]
    assert v["holdout_wired_to_gate"] is expected


def test_memory_block_reports_unreachable_without_raising(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:59999")
    m = _memory_block()
    assert m["reachable"] is False
    assert m["error"]
    assert m["collections"] == []
