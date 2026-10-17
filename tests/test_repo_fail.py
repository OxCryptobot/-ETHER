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
    assert "fail" not in text.lower()
    assert "regex" not in text


def test_a_tool_result_stays_inside_the_budget() -> None:
    from core.kernel.repo_fail import fit, opening

    huge = {"ok": True, "body": "x" * 5000}
    text = fit(opening(), huge, budget=500)
    assert len(text) <= 500
    assert "grep" in text


def test_a_read_is_the_matching_lines_not_the_file(tmp_path: Path) -> None:
    from core.kernel.repo_fail import act

    ws = tmp_path / "ws"
    ws.mkdir()
    lines = ["HEAD marker that must stay out"] + ["padding"] * 40 + ["the failing symbol is here"] + ["tail"]
    (ws / "mod.py").write_text("\n".join(lines), encoding="utf-8")
    obs = act(ws, "read_file", {"path": "mod.py", "focus": "failing symbol"})
    assert "failing symbol" in obs["body"]
    assert "HEAD marker" not in obs["body"]


def test_yesterdays_trace_is_dropped_and_today_is_only_the_trace() -> None:
    from datetime import datetime, timedelta, timezone

    from core.kernel.repo_fail import start_prompt, trace_text

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    state = {"trace": {"day": yesterday, "hits": ["greeter.py:4:return"], "tools": ["grep"]}}
    assert trace_text(state) == ""
    assert "greeter" not in start_prompt(state)
    state["trace"]["day"] = datetime.now(timezone.utc).date().isoformat()
    state["trace"]["assertion"] = "assert greet() == 'Hello, World!'"
    shown = start_prompt(state)
    assert "greeter.py" in shown
    assert "assert greet" in shown
    assert "Last failure" not in shown


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


def test_an_invented_path_is_not_a_read(tmp_path: Path) -> None:
    from core.kernel.repo_fail import run

    def invented(prompt: str, n: int = 180) -> str:
        if "hits" in prompt:
            return json.dumps({"tool": "read_file", "args": {"path": "test/test.py"}})
        return json.dumps({"tool": "grep", "args": {"pattern": "Hello"}})

    row = run(_root(tmp_path), invented, steps=2)
    assert row["honest"] is False
    assert "apply_patch" not in row["tools"]


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
    assert second["tools"][0] == "apply_patch"
    assert third["note"] == "repo_fail_repeated"
    assert third["honest"] is False
    assert calls["n"] == 4


def test_a_miss_is_not_searched_again(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    from core.kernel.repo_fail import run

    root = _root(tmp_path)
    (root / "artifacts").mkdir(parents=True)
    (root / "artifacts" / "repo_fail.json").write_text(
        json.dumps({
            "passes": [],
            "trace": {
                "day": datetime.now(timezone.utc).date().isoformat(),
                "pattern": "fail",
                "hits": [],
                "tools": ["grep"],
            },
        }),
        encoding="utf-8",
    )
    calls = {"n": 0}

    def ask(prompt: str, n: int = 180) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            assert "do not search again: fail" in prompt
            return json.dumps({"tool": "grep", "args": {"pattern": "fail"}})
        if "body" in prompt:
            return json.dumps({
                "tool": "apply_patch",
                "args": {
                    "path": "greeter.py",
                    "old": 'return f"Hello {name}"',
                    "new": 'return f"Hello, {name}!"',
                },
            })
        if '"hits"' in prompt:
            return json.dumps({"tool": "read_file", "args": {"path": "greeter.py"}})
        return json.dumps({"tool": "grep", "args": {"pattern": "Hello"}})

    row = run(root, ask)
    assert row["honest"] is True
    assert row["tools"].count("grep") == 2


def test_the_same_miss_stops(tmp_path: Path) -> None:
    from core.kernel.repo_fail import run

    def again(prompt: str, n: int = 180) -> str:
        return json.dumps({"tool": "grep", "args": {"pattern": "fail"}})

    row = run(_root(tmp_path), again, steps=8)
    assert row["honest"] is False
    assert row["tools"].count("grep") == 4


def test_a_read_without_a_hit_stops(tmp_path: Path) -> None:
    from core.kernel.repo_fail import run

    def invented(prompt: str, n: int = 180) -> str:
        return json.dumps({"tool": "read_file", "args": {"path": "src/main.rs"}})

    row = run(_root(tmp_path), invented, steps=8)
    assert row["honest"] is False
    assert row["tools"].count("read_file") == 3


def test_one_read_then_a_different_tool(tmp_path: Path) -> None:
    from core.kernel.repo_fail import load_state, run, start_prompt

    root = _root(tmp_path)

    def ask(prompt: str, n: int = 180) -> str:
        if "already read" in prompt:
            return json.dumps({
                "tool": "apply_patch",
                "args": {
                    "path": "greeter.py",
                    "old": 'return f"Hello {name}"',
                    "new": 'return f"Hello, {name}!"',
                },
            })
        if "body" in prompt:
            return json.dumps({"tool": "read_file", "args": {"path": "greeter.py"}})
        if "hits" in prompt:
            return json.dumps({"tool": "read_file", "args": {"path": "greeter.py"}})
        return json.dumps({"tool": "grep", "args": {"pattern": "Hello"}})

    row = run(root, ask)
    assert row["honest"] is True
    assert row["tools"].count("read_file") == 2
    assert row["tools"][-1] == "apply_patch"
    shown = start_prompt(load_state(root))
    assert "read_file, read_file" not in shown
    assert "Hello {name}" in shown


def test_the_same_read_stops(tmp_path: Path) -> None:
    from core.kernel.repo_fail import run

    def again(prompt: str, n: int = 180) -> str:
        if "hits" in prompt or "body" in prompt or "already read" in prompt:
            return json.dumps({"tool": "read_file", "args": {"path": "greeter.py"}})
        return json.dumps({"tool": "grep", "args": {"pattern": "Hello"}})

    row = run(_root(tmp_path), again, steps=8)
    assert row["honest"] is False
    assert row["tools"].count("read_file") == 4


def test_alternating_bad_reads_stop(tmp_path: Path) -> None:
    from core.kernel.repo_fail import run

    paths = ["src/main.rs", "conftest.py", "tests/missing.py"]
    calls = {"n": 0}

    def alternate(prompt: str, n: int = 180) -> str:
        path = paths[calls["n"] % len(paths)]
        calls["n"] += 1
        return json.dumps({"tool": "read_file", "args": {"path": path}})

    row = run(_root(tmp_path), alternate, steps=8)
    assert row["honest"] is False
    assert row["tools"].count("read_file") == 3


def test_a_helper_body_is_not_memory(tmp_path: Path) -> None:
    from core.kernel.repo_fail import load_state, run, start_prompt

    root = _root(tmp_path)

    def ask(prompt: str, n: int = 180) -> str:
        if "hits" in prompt and "body" not in prompt:
            return json.dumps({"tool": "read_file", "args": {"path": "tests/conftest.py"}})
        return json.dumps({"tool": "grep", "args": {"pattern": "import"}})

    row = run(root, ask, steps=2)
    assert row["honest"] is False
    shown = start_prompt(load_state(root))
    assert "sys.path.insert" not in shown
    assert "from greeter import greet" in shown
