"""The model writes the function. The tests keep it. Nothing is injected."""
from __future__ import annotations

from pathlib import Path

from core.agent.sota import run


def test_the_model_writes_it(tmp_path: Path) -> None:
    src = Path("core/kernel/context_budget.py").read_text(encoding="utf-8")
    target = tmp_path / "core" / "kernel"
    target.mkdir(parents=True)
    (target / "context_budget.py").write_text(src, encoding="utf-8")

    def ask(prompt: str, n: int = 240) -> str:
        return "def packed_count(text: str) -> int:\n    return text.count('### ')\n"

    row = run(tmp_path, ask)
    assert "packed_count" in row["batch"]
    body = (target / "context_budget.py").read_text(encoding="utf-8")
    assert "def packed_count" in body


def test_a_non_function_is_not_kept(tmp_path: Path) -> None:
    target = tmp_path / "core" / "kernel"
    target.mkdir(parents=True)
    (target / "context_budget.py").write_text("def fits(text: str) -> bool:\n    return True\n", encoding="utf-8")

    def ask(prompt: str, n: int = 240) -> str:
        return "I am not sure"

    before = (target / "context_budget.py").read_text(encoding="utf-8")
    row = run(tmp_path, ask)
    assert row["ok"] is False
    assert (target / "context_budget.py").read_text(encoding="utf-8") == before


def test_a_failed_test_is_skipped(tmp_path: Path) -> None:
    from core.agent.sota import next_goal, remember

    kernel = tmp_path / "core" / "kernel"
    kernel.mkdir(parents=True)
    (kernel / "context_budget.py").write_text("def fits(text: str) -> bool:\n    return True\n", encoding="utf-8")
    (kernel / "agent.py").write_text("def run() -> None:\n    return None\n", encoding="utf-8")
    remember(tmp_path, "describe_context_budget", "tests failed", kept=False)
    goal = next_goal(tmp_path)
    assert goal is None or goal["id"] != "describe_context_budget"


def test_kept_files_are_tracked(tmp_path: Path) -> None:
    from core.agent.sota import load, remember

    remember(tmp_path, "same_count", "tests passed", kept=True, file="core/kernel/context_budget.py")
    state = load(tmp_path)
    assert "core/kernel/context_budget.py" in state["files"]


def test_a_skip_is_permanent(tmp_path: Path) -> None:
    from core.agent.sota import load, next_goal, remember

    kernel = tmp_path / "core" / "kernel"
    kernel.mkdir(parents=True)
    (kernel / "extra_tools.py").write_text("def run() -> None:\n    return None\n", encoding="utf-8")
    remember(tmp_path, "describe_extra_tools", "tests failed", kept=False)
    state = load(tmp_path)
    assert "describe_extra_tools" in state["skipped"]
    goal = next_goal(tmp_path)
    assert goal is None or goal["id"] != "describe_extra_tools"


def test_the_queue_grows_when_empty(tmp_path: Path) -> None:
    from core.agent.sota import generate, recall, remember

    kernel = tmp_path / "core" / "kernel"
    kernel.mkdir(parents=True)
    (kernel / "agent.py").write_text("def run() -> None:\n    return None\n", encoding="utf-8")
    remember(tmp_path, "packed_count", "tests passed", kept=True, file="core/kernel/context_budget.py")
    assert "passed" in recall(tmp_path)
    goal = generate(tmp_path, set(), set())
    assert goal is not None
    assert goal["symbol"] == "describe"
    assert "agent" in goal["id"]
