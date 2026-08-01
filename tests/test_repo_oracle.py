"""Phase B — repo oracle unit tests (no LLM, no live tree writes)."""

from __future__ import annotations

from pathlib import Path

from core.repo_oracle import (
    apply_file_map,
    parse_file_markers,
    score_from_marked_code,
    score_repo_edit,
    validate_file_map,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "repo_oracle_toy"


def test_parse_file_markers_two_files():
    code = """# file: a.py
def a():
    return 1

# file: b.py
def b():
    return 2
"""
    m = parse_file_markers(code)
    assert set(m) == {"a.py", "b.py"}
    assert "def a" in m["a.py"]


def test_validate_blocks_parent_traversal():
    r = validate_file_map({"../secret.py": "x = 1"})
    assert r["ok"] is False


def test_toy_fixture_fails_baseline():
    broken = (FIXTURE / "greeter.py").read_text(encoding="utf-8")
    result = score_repo_edit(
        {"greeter.py": broken},
        fixture_root=FIXTURE,
        test_args=["tests"],
        timeout=30,
    )
    assert result["ok"] is False
    assert result["score"] < 1.0
    assert result["oracle"] == "project_pytest"


def test_toy_fixture_passes_after_fix():
    fixed = '''"""Fixed greeter."""

def greet(name: str) -> str:
    return f"Hello, {name}!"
'''
    result = score_repo_edit(
        {"greeter.py": fixed},
        fixture_root=FIXTURE,
        test_args=["tests"],
        timeout=30,
    )
    assert result["ok"] is True
    assert result["score"] == 1.0
    assert "greeter.py" in (result.get("written") or [])


def test_score_from_marked_code_fixed():
    code = '''# file: greeter.py
def greet(name: str) -> str:
    return f"Hello, {name}!"
'''
    result = score_from_marked_code(
        code,
        fixture_root=FIXTURE,
        test_args=["tests"],
        timeout=30,
    )
    assert result["ok"] is True
    assert result["score"] == 1.0


# --- second fixture: wallet (class/state) ---

WALLET = ROOT / "fixtures" / "repo_oracle_wallet"

FIXED_WALLET = '''\
"""Toy wallet — fixed."""


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


def test_wallet_baseline_fails():
    broken = (WALLET / "wallet.py").read_text(encoding="utf-8")
    r = score_repo_edit(
        {"wallet.py": broken}, fixture_root=WALLET, test_args=["tests"], timeout=30
    )
    assert r["ok"] is False
    assert r["score"] < 1.0
    assert r["oracle"] == "project_pytest"


def test_wallet_fixed_passes():
    r = score_repo_edit(
        {"wallet.py": FIXED_WALLET},
        fixture_root=WALLET,
        test_args=["tests"],
        timeout=30,
    )
    assert r["ok"] is True
    assert r["score"] == 1.0


def test_wallet_marked_multi_file():
    code = "# file: wallet.py\n" + FIXED_WALLET
    r = score_from_marked_code(
        code, fixture_root=WALLET, test_args=["tests"], timeout=30
    )
    assert r["ok"] is True
    assert r["score"] == 1.0
