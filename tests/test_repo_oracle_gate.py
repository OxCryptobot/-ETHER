"""Phase B close-out — apply_repo_oracle_gate forces fail on project-test miss."""

from __future__ import annotations

from pathlib import Path

from core.pipeline_hooks import apply_repo_oracle_gate

ROOT = Path(__file__).resolve().parents[1]
GREETER = ROOT / "fixtures" / "repo_oracle_toy"
WALLET = ROOT / "fixtures" / "repo_oracle_wallet"


def test_gate_inactive_when_disabled(monkeypatch):
    monkeypatch.delenv("ETHER_REPO_ORACLE", raising=False)
    monkeypatch.delenv("ETHER_REPO_ORACLE_FIXTURE", raising=False)
    g = apply_repo_oracle_gate(
        "def x(): pass", "obj", execution_score=1.0, verification_score=1.0, confidence=1.0
    )
    assert g.get("active") is False


def test_gate_fails_broken_greeter(monkeypatch):
    monkeypatch.setenv("ETHER_REPO_ORACLE", "1")
    monkeypatch.setenv("ETHER_REPO_ORACLE_FIXTURE", str(GREETER))
    monkeypatch.setenv("ETHER_REPO_ORACLE_AS_PATH", "greeter.py")
    broken = (GREETER / "greeter.py").read_text(encoding="utf-8")
    g = apply_repo_oracle_gate(
        broken, "fix greeter", execution_score=1.0, verification_score=1.0, confidence=0.9
    )
    assert g["active"] is True
    assert g["ok"] is False
    assert g["fail_kind"] == "repo_oracle"
    assert g["repo_oracle_ok"] is False
    assert g["verification_score"] < 1.0


def test_gate_passes_fixed_greeter(monkeypatch):
    monkeypatch.setenv("ETHER_REPO_ORACLE", "1")
    monkeypatch.setenv("ETHER_REPO_ORACLE_FIXTURE", str(GREETER))
    monkeypatch.setenv("ETHER_REPO_ORACLE_AS_PATH", "greeter.py")
    fixed = 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n'
    g = apply_repo_oracle_gate(
        fixed, "fix greeter", execution_score=1.0, verification_score=1.0, confidence=0.9
    )
    assert g["active"] is True
    assert g["ok"] is True
    assert g["repo_oracle_ok"] is True
    assert g["fail_kind"] == ""
    assert g["score"] == 1.0


def test_gate_fails_broken_wallet(monkeypatch):
    monkeypatch.setenv("ETHER_REPO_ORACLE", "1")
    monkeypatch.setenv("ETHER_REPO_ORACLE_FIXTURE", str(WALLET))
    monkeypatch.setenv("ETHER_REPO_ORACLE_AS_PATH", "wallet.py")
    broken = (WALLET / "wallet.py").read_text(encoding="utf-8")
    g = apply_repo_oracle_gate(
        broken, "fix wallet", execution_score=1.0, verification_score=1.0, confidence=0.9
    )
    assert g["active"] is True
    assert g["ok"] is False
    assert g["fail_kind"] == "repo_oracle"
    assert g["repo_oracle_ok"] is False


def test_gate_passes_fixed_wallet(monkeypatch):
    monkeypatch.setenv("ETHER_REPO_ORACLE", "1")
    monkeypatch.setenv("ETHER_REPO_ORACLE_FIXTURE", str(WALLET))
    monkeypatch.setenv("ETHER_REPO_ORACLE_AS_PATH", "wallet.py")
    fixed = '''
class Wallet:
    def __init__(self, balance: float = 0.0) -> None:
        self.balance = float(balance)
    def deposit(self, amount: float) -> float:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        self.balance = self.balance + amount
        return self.balance
    def withdraw(self, amount: float) -> float:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        if amount > self.balance:
            raise ValueError("insufficient funds")
        self.balance = self.balance - amount
        return self.balance
'''
    g = apply_repo_oracle_gate(
        fixed, "fix wallet", execution_score=1.0, verification_score=1.0, confidence=0.9
    )
    assert g["active"] is True
    assert g["ok"] is True
    assert g["repo_oracle_ok"] is True
    assert g["score"] == 1.0
