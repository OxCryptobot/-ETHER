"""Phase C slice 1 — tool-first runtime (no LLM)."""

from __future__ import annotations

from pathlib import Path

from core.tool_runtime import ToolRuntime, parse_action, tool_runtime_enabled

ROOT = Path(__file__).resolve().parents[1]
GREETER = ROOT / "fixtures" / "repo_oracle_toy"
WALLET = ROOT / "fixtures" / "repo_oracle_wallet"

FIXED_GREETER = 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n'

FIXED_WALLET = '''\
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


def test_parse_action_json():
    a = parse_action('{"tool": "read_file", "args": {"path": "greeter.py"}}')
    assert a["tool"] == "read_file"
    assert a["args"]["path"] == "greeter.py"


def test_parse_action_fence():
    a = parse_action('Sure.\n```json\n{"tool": "list_files", "args": {}}\n```\n')
    assert a["tool"] == "list_files"


def test_parse_action_fail_closed():
    a = parse_action("I will now fix the code carefully.")
    assert a["tool"] == "done"


def test_runtime_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ETHER_TOOL_RUNTIME", raising=False)
    assert tool_runtime_enabled() is False


def test_scripted_fix_greeter():
    """Scripted decide_fn: list → read → write fixed → run_tests → done."""
    plan = [
        {"tool": "list_files", "args": {}},
        {"tool": "read_file", "args": {"path": "greeter.py"}},
        {"tool": "write_file", "args": {"path": "greeter.py", "content": FIXED_GREETER}},
        {"tool": "run_tests", "args": {}},
    ]
    it = iter(plan)

    def decide(_messages):
        try:
            return next(it)
        except StopIteration:
            return {"tool": "done", "args": {"reason": "exhausted"}}

    rt = ToolRuntime(
        fixture_root=GREETER,
        decide_fn=decide,
        max_steps=6,
        pytest_timeout=30,
    )
    result = rt.run("fix greeter so tests pass")
    assert result.ok is True
    assert result.score == 1.0
    assert result.n_steps == 4
    tools = [s.tool for s in result.steps]
    assert tools == ["list_files", "read_file", "write_file", "run_tests"]


def test_scripted_fix_wallet():
    plan = [
        {"tool": "read_file", "args": {"path": "wallet.py"}},
        {"tool": "write_file", "args": {"path": "wallet.py", "content": FIXED_WALLET}},
        {"tool": "run_tests", "args": {}},
    ]
    it = iter(plan)

    def decide(_messages):
        try:
            return next(it)
        except StopIteration:
            return {"tool": "done", "args": {"reason": "stop"}}

    rt = ToolRuntime(
        fixture_root=WALLET,
        decide_fn=decide,
        max_steps=5,
        pytest_timeout=30,
    )
    result = rt.run("fix wallet")
    assert result.ok is True
    assert result.score == 1.0


def test_path_escape_refused():
    def decide(_m):
        return {"tool": "read_file", "args": {"path": "../secrets.env"}}

    rt = ToolRuntime(fixture_root=GREETER, decide_fn=decide, max_steps=2)
    result = rt.run("probe")
    assert result.steps[0].ok is False
    assert "refused" in str(result.steps[0].observation.get("error", "")).lower() or \
           "parent" in str(result.steps[0].observation.get("error", "")).lower()


def test_max_steps_without_fix():
    def decide(_m):
        return {"tool": "list_files", "args": {}}

    rt = ToolRuntime(fixture_root=GREETER, decide_fn=decide, max_steps=3)
    result = rt.run("spin")
    assert result.ok is False
    assert result.error == "max_steps"
    assert result.n_steps == 3
