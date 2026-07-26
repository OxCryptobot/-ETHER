"""Automated health check unit tests (no live Docker required)."""

from __future__ import annotations

from core.health_check import check_python, check_memory_dirs, run_health_checks


def test_python_check_ok():
    c = check_python()
    assert c.id == "python"
    assert c.ok is True


def test_memory_dirs_creates():
    c = check_memory_dirs()
    assert c.ok is True


def test_run_health_skip_sandbox(monkeypatch):
    monkeypatch.setenv("ETHER_HEALTH_SKIP_SANDBOX", "1")
    report = run_health_checks(include_sandbox_smoke=False)
    assert "status" in report
    assert "checks" in report
    assert report["counts"]["total"] >= 8
    ids = {c["id"] for c in report["checks"]}
    assert "python" in ids
    assert "sandbox_smoke" not in ids
