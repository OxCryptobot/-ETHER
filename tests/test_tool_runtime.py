"""Phase C/G — tool-first runtime tests (no live LLM required)."""

from __future__ import annotations

import json as _json
from pathlib import Path

from core.tool_runtime import (
    TOOL_SPECS,
    ToolRuntime,
    make_llm_decide_fn,
    parse_action,
    tool_runtime_enabled,
)

ROOT = Path(__file__).resolve().parents[1]
GREETER = ROOT / "fixtures" / "repo_oracle_toy"
WALLET = ROOT / "fixtures" / "repo_oracle_wallet"

FIXED_GREETER = 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n'

FIXED_WALLET = (
    "class Wallet:\n"
    "    def __init__(self, balance: float = 0.0) -> None:\n"
    "        self.balance = float(balance)\n"
    "    def deposit(self, amount: float) -> float:\n"
    "        if amount < 0:\n"
    "            raise ValueError(\"amount must be non-negative\")\n"
    "        self.balance = self.balance + amount\n"
    "        return self.balance\n"
    "    def withdraw(self, amount: float) -> float:\n"
    "        if amount < 0:\n"
    "            raise ValueError(\"amount must be non-negative\")\n"
    "        if amount > self.balance:\n"
    "            raise ValueError(\"insufficient funds\")\n"
    "        self.balance = self.balance - amount\n"
    "        return self.balance\n"
)


def test_tool_specs_include_sprint_tools():
    names = {t["name"] for t in TOOL_SPECS}
    for n in ("grep", "glob", "apply_patch", "rollback"):
        assert n in names


def test_parse_action_json():
    a = parse_action('{"tool": "read_file", "args": {"path": "greeter.py"}}')
    assert a["tool"] == "read_file"
    assert a["args"]["path"] == "greeter.py"


def test_parse_action_fence():
    a = parse_action('Sure.\n```json\n{"tool": "list_files", "args": {}}\n```\n')
    assert a["tool"] == "list_files"


def test_parse_action_fail_closed():
    a = parse_action("I will now fix the code carefully.")
    assert a["tool"] == "_retry"


def test_runtime_default_on_under_wheels(monkeypatch):
    """Package 1A: tool-first is the required default under training wheels."""
    monkeypatch.delenv("ETHER_TOOL_RUNTIME", raising=False)
    monkeypatch.setenv("ETHER_TRAINING_WHEELS", "1")
    assert tool_runtime_enabled() is True

    monkeypatch.setenv("ETHER_TOOL_RUNTIME", "0")
    assert tool_runtime_enabled() is False

    monkeypatch.setenv("ETHER_TOOL_RUNTIME", "1")
    assert tool_runtime_enabled() is True

    monkeypatch.delenv("ETHER_TOOL_RUNTIME", raising=False)
    monkeypatch.setenv("ETHER_TRAINING_WHEELS", "0")
    assert tool_runtime_enabled() is False


def test_scripted_fix_greeter():
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
        fixture_root=GREETER, decide_fn=decide, max_steps=6, pytest_timeout=30
    )
    result = rt.run("fix greeter so tests pass")
    assert result.ok is True
    assert result.score == 1.0
    assert result.n_steps == 4


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
        fixture_root=WALLET, decide_fn=decide, max_steps=5, pytest_timeout=30
    )
    result = rt.run("fix wallet")
    assert result.ok is True
    assert result.score == 1.0


def test_apply_patch_fail_closed_no_match():
    def decide(_m):
        return {
            "tool": "apply_patch",
            "args": {
                "path": "greeter.py",
                "old": "THIS_STRING_DOES_NOT_EXIST_XYZ",
                "new": "x",
            },
        }

    rt = ToolRuntime(
        fixture_root=GREETER, decide_fn=decide, max_steps=1, pytest_timeout=30
    )
    result = rt.run("bad patch")
    assert result.steps[0].ok is False
    err = str(result.steps[0].observation.get("error", "")).lower()
    assert "not found" in err


def test_rollback_restores_prior_content():
    calls = {"n": 0}

    def decide(_m):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "tool": "write_file",
                "args": {"path": "greeter.py", "content": "# broken\n"},
            }
        if calls["n"] == 2:
            return {"tool": "rollback", "args": {}}
        if calls["n"] == 3:
            return {"tool": "read_file", "args": {"path": "greeter.py"}}
        return {"tool": "done", "args": {"reason": "check"}}

    rt = ToolRuntime(
        fixture_root=GREETER, decide_fn=decide, max_steps=4, pytest_timeout=30
    )
    result = rt.run("rollback probe")
    assert any(s.tool == "rollback" and s.ok for s in result.steps)
    read = [s for s in result.steps if s.tool == "read_file"][0]
    content = str(read.observation.get("content") or "")
    assert "# broken" not in content


def test_grep_finds_symbol():
    def decide(_m):
        return {"tool": "grep", "args": {"pattern": "def ", "path": "."}}

    rt = ToolRuntime(
        fixture_root=GREETER, decide_fn=decide, max_steps=1, pytest_timeout=30
    )
    result = rt.run("grep")
    assert result.steps[0].ok is True
    hits = result.steps[0].observation.get("hits") or []
    assert len(hits) >= 1


def test_glob_py_files():
    def decide(_m):
        return {"tool": "glob", "args": {"pattern": "**/*.py"}}

    rt = ToolRuntime(
        fixture_root=GREETER, decide_fn=decide, max_steps=1, pytest_timeout=30
    )
    result = rt.run("glob")
    assert result.steps[0].ok is True
    files = result.steps[0].observation.get("files") or []
    assert any(f.endswith(".py") for f in files)


def test_path_escape_refused():
    def decide(_m):
        return {"tool": "read_file", "args": {"path": "../secrets.env"}}

    rt = ToolRuntime(fixture_root=GREETER, decide_fn=decide, max_steps=2)
    result = rt.run("probe")
    assert result.steps[0].ok is False
    err = str(result.steps[0].observation.get("error", "")).lower()
    assert "refused" in err or "parent" in err


def test_max_steps_without_fix():
    def decide(_m):
        return {"tool": "list_files", "args": {}}

    rt = ToolRuntime(fixture_root=GREETER, decide_fn=decide, max_steps=3)
    result = rt.run("spin")
    assert result.ok is False
    assert result.error == "max_steps"
    assert result.n_steps == 3


def test_make_llm_decide_fn_with_mock_call():
    def fake_call(messages):
        assert messages
        return '{"tool": "list_files", "args": {}}'

    decide = make_llm_decide_fn(call_fn=fake_call)
    action = decide([{"role": "user", "content": "go"}])
    assert action["tool"] == "list_files"


def test_make_llm_decide_fn_parses_messy_output():
    def fake_call(_m):
        return (
            "I will list files first.\n"
            "```json\n"
            '{"tool": "read_file", "args": {"path": "greeter.py"}}\n'
            "```\n"
        )

    decide = make_llm_decide_fn(call_fn=fake_call)
    action = decide([{"role": "user", "content": "x"}])
    assert action["tool"] == "read_file"
    assert action["args"]["path"] == "greeter.py"


def test_llm_decide_fn_scripted_fix_greeter():
    fixed = 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n'
    plan = [
        '{"tool": "list_files", "args": {}}',
        '{"tool": "read_file", "args": {"path": "greeter.py"}}',
        _json.dumps(
            {"tool": "write_file", "args": {"path": "greeter.py", "content": fixed}}
        ),
        '{"tool": "run_tests", "args": {}}',
    ]
    it = iter(plan)

    def fake_call(_messages):
        try:
            return next(it)
        except StopIteration:
            return '{"tool": "done", "args": {"reason": "exhausted"}}'

    decide = make_llm_decide_fn(call_fn=fake_call)
    rt = ToolRuntime(
        fixture_root=GREETER, decide_fn=decide, max_steps=6, pytest_timeout=30
    )
    result = rt.run("fix greeter")
    assert result.ok is True
    assert result.score == 1.0
