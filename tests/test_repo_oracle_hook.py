"""Phase B slice 2 — repo_oracle_hook gating."""

from __future__ import annotations

from pathlib import Path

from core.repo_oracle_hook import evaluate_after_sandbox, repo_oracle_enabled


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "repo_oracle_toy"


def test_hook_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ETHER_REPO_ORACLE", raising=False)
    monkeypatch.delenv("ETHER_REPO_ORACLE_FIXTURE", raising=False)
    assert repo_oracle_enabled() is False
    assert evaluate_after_sandbox("def greet(name):\n    return name\n") is None


def test_hook_fails_broken_greeter(monkeypatch):
    monkeypatch.setenv("ETHER_REPO_ORACLE", "1")
    monkeypatch.setenv("ETHER_REPO_ORACLE_FIXTURE", str(FIXTURE))
    monkeypatch.setenv("ETHER_REPO_ORACLE_AS_PATH", "greeter.py")
    broken = (FIXTURE / "greeter.py").read_text(encoding="utf-8")
    out = evaluate_after_sandbox(broken)
    assert out is not None
    assert out["ok"] is False
    assert out["score"] < 1.0


def test_hook_passes_fixed_greeter(monkeypatch):
    monkeypatch.setenv("ETHER_REPO_ORACLE", "1")
    monkeypatch.setenv("ETHER_REPO_ORACLE_FIXTURE", str(FIXTURE))
    monkeypatch.setenv("ETHER_REPO_ORACLE_AS_PATH", "greeter.py")
    fixed = 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n'
    out = evaluate_after_sandbox(fixed)
    assert out is not None
    assert out["ok"] is True
    assert out["score"] == 1.0
