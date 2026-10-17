"""The ladder is done. The next edit finds a failing project without being handed the path."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

FIXTURE = Path("fixtures/repo_oracle_toy")


def _root(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / "fixtures" / "repo_oracle_toy")
    return tmp_path


def test_the_opening_prompt_does_not_name_the_file() -> None:
    from core.kernel.repo_fail import opening

    text = opening()
    assert "greeter" not in text
    assert "fixtures" not in text
    assert "Hello" not in text
    assert "return f" not in text


def test_a_tool_result_stays_inside_the_budget() -> None:
    from core.kernel.repo_fail import fit, opening

    huge = {"ok": True, "body": "x" * 5000}
    text = fit(opening(), huge, budget=500)
    assert len(text) <= 500
    assert "grep" in text


def _ask(prompt: str, n: int = 180) -> str:
    if "body" in prompt:
        return json.dumps({
            "tool": "apply_patch",
            "args": {
                "path": "greeter.py",
                "old": 'return f"Hello {name}"',
                "new": 'return f"Hello, {name}!"',
            },
        })
    if "hits" in prompt:
        path = "greeter.py" if "greeter.py" in prompt else "tests/test_greeter.py"
        return json.dumps({"tool": "read_file", "args": {"path": path}})
    return json.dumps({"tool": "grep", "args": {"pattern": "Hello"}})


def test_the_model_has_to_find_the_file(tmp_path: Path) -> None:
    from core.kernel.repo_fail import run

    row = run(_root(tmp_path), _ask)
    assert row["honest"] is True
    assert row["tools"][0] == "grep"
    assert "read_file" in row["tools"]
    assert row["tools"].index("read_file") < row["tools"].index("apply_patch")
    assert row["file"] == "greeter.py"
    assert 'Hello {name}' in FIXTURE.joinpath("greeter.py").read_text(encoding="utf-8")


def test_a_patch_before_a_read_is_not_a_pass(tmp_path: Path) -> None:
    from core.kernel.repo_fail import run

    def early(prompt: str, n: int = 180) -> str:
        return json.dumps({
            "tool": "apply_patch",
            "args": {
                "path": "greeter.py",
                "old": 'return f"Hello {name}"',
                "new": 'return f"Hello, {name}!"',
            },
        })

    row = run(_root(tmp_path), early, steps=2)
    assert row["honest"] is False
    assert (tmp_path / "repo_fail_ws" / "greeter.py").read_text(encoding="utf-8").count('Hello {name}') == 1


def test_the_same_failure_can_pass_twice(tmp_path: Path) -> None:
    from core.kernel.repo_fail import run

    calls = {"n": 0}

    def counting(prompt: str, n: int = 180) -> str:
        calls["n"] += 1
        return _ask(prompt, n)

    root = _root(tmp_path)
    first = run(root, counting)
    second = run(root, counting)
    third = run(root, counting)
    assert first["honest"] is True and first["passes"] == 1
    assert second["honest"] is True and second["passes"] == 2
    assert third["note"] == "repo_fail_repeated"
    assert third["honest"] is False
    assert calls["n"] == 6
