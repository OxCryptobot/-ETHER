"""The ladder advances, and the prompt does not contain the answer."""
import json
from pathlib import Path

from core.kernel.curriculum import TASKS, checker_for, mark_passed, next_task


def test_prompt_does_not_contain_the_answer() -> None:
    for task in TASKS:
        assert task["banned"] not in task["prompt"]
        assert task["banned"] not in task["source"]
        for body in (task.get("also") or {}).values():
            assert task["banned"] not in body


def test_fresh_root_starts_at_add(tmp_path: Path) -> None:
    task = next_task(tmp_path)
    assert task is not None and task["id"] == "add"


def test_two_honest_passes_skip_add(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "honest_history.json").write_text(json.dumps({
        "items": [{"ts": "t1", "honest": True}, {"ts": "t2", "honest": True}],
    }), encoding="utf-8")
    task = next_task(tmp_path)
    assert task is not None and task["id"] == "clamp"


def test_passed_task_is_not_repeated(tmp_path: Path) -> None:
    mark_passed(tmp_path, "add")
    mark_passed(tmp_path, "clamp")
    assert next_task(tmp_path)["id"] == "sign"
    mark_passed(tmp_path, "sign")
    assert next_task(tmp_path)["id"] == "span"
    mark_passed(tmp_path, "span")
    assert next_task(tmp_path)["id"] == "uniq"
    mark_passed(tmp_path, "uniq")
    assert next_task(tmp_path)["id"] == "above"
    mark_passed(tmp_path, "above")
    task = next_task(tmp_path)
    assert task is not None and task["id"] == "merge" and task["repo"] is True
    mark_passed(tmp_path, "merge")
    assert next_task(tmp_path)["id"] == "merge"
    from core.kernel.worktree import tree_path

    fixed = (
        "def merge_intervals(intervals):\n"
        "    if not intervals:\n"
        "        return []\n"
        "    out = []\n"
        "    for start, end in sorted(intervals):\n"
        "        if not out or start > out[-1][1]:\n"
        "            out.append((start, end))\n"
        "        else:\n"
        "            ps, pe = out[-1]\n"
        "            out[-1] = (ps, max(pe, end))\n"
        "    return out\n"
    )
    dest = tree_path(tmp_path)
    dest.mkdir()
    (dest / "intervals.py").write_text(fixed, encoding="utf-8")
    assert next_task(tmp_path) is None


def test_a_kept_file_is_not_edited_again(tmp_path: Path) -> None:
    from core.kernel.curriculum import hold_status, mark_passed
    from core.kernel.worktree import seal, tree_path

    for name in ("add", "clamp", "sign", "span", "uniq", "above", "merge"):
        mark_passed(tmp_path, name)
    assert next_task(tmp_path)["id"] == "merge"
    fixed = (
        "def merge_intervals(intervals):\n"
        "    if not intervals:\n"
        "        return []\n"
        "    out = []\n"
        "    for start, end in intervals:\n"
        "        if out and start <= out[-1][1]:\n"
        "            ps, pe = out[-1]\n"
        "            out[-1] = (ps, max(pe, end))\n"
        "        else:\n"
        "            out.append((start, end))\n"
        "    return out\n"
    )
    ws = tree_path(tmp_path)
    ws.mkdir()
    (ws / "intervals.py").write_text(fixed, encoding="utf-8")
    (ws / "tests").mkdir()
    row = seal(tmp_path, "merge")
    assert row["rc"] == 0
    assert (ws / ".git").is_dir()
    assert not (tmp_path / ".git").exists()
    assert next_task(tmp_path) is None
    status = hold_status(tmp_path)
    assert status["persisted"] is True
    assert status["note"] == "kept"
    assert (ws / "intervals.py").read_text(encoding="utf-8") == fixed


def test_merge_is_a_repo_file_and_the_prompt_has_no_patch(tmp_path: Path) -> None:
    import subprocess
    import sys

    from core.kernel.curriculum import diagnose, write_task

    task = next(t for t in TASKS if t["id"] == "merge")
    assert task["banned"] not in task["source"]
    assert task["banned"] not in task["prompt"]
    assert task["banned"] not in task["also"]["tests/test_merge.py"]
    note = diagnose(task, task["source"])
    assert "expected [(1, 5)]" in note
    assert task["banned"] not in note
    write_task(tmp_path, task)
    assert (tmp_path / "intervals.py").is_file()
    assert (tmp_path / "tests" / "test_merge.py").is_file()
    broken = subprocess.run([sys.executable, str(tmp_path / "tests" / "test_merge.py")], cwd=str(tmp_path), capture_output=True, text=True)
    assert broken.returncode != 0
    (tmp_path / "intervals.py").write_text(
        "def merge_intervals(intervals):\n"
        "    if not intervals:\n"
        "        return []\n"
        "    out = []\n"
        "    for start, end in sorted(intervals):\n"
        "        if not out or start > out[-1][1]:\n"
        "            out.append((start, end))\n"
        "        else:\n"
        "            ps, pe = out[-1]\n"
        "            out[-1] = (ps, max(pe, end))\n"
        "    return out\n",
        encoding="utf-8",
    )
    fixed = subprocess.run([sys.executable, str(tmp_path / "tests" / "test_merge.py")], cwd=str(tmp_path), capture_output=True, text=True)
    assert fixed.returncode == 0


def test_span_uses_a_second_file_and_a_failed_edit_reverts(tmp_path: Path) -> None:
    import subprocess
    import sys

    from core.kernel.product_loop import run_edit

    task = next(t for t in TASKS if t["id"] == "span")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "bounds.py").write_text(task["source"], encoding="utf-8")
    (ws / "test_bounds.py").write_text(task["also"]["test_bounds.py"], encoding="utf-8")
    broken = subprocess.run([sys.executable, str(ws / "test_bounds.py")], cwd=str(ws), capture_output=True, text=True)
    assert broken.returncode != 0
    row = run_edit(ws, "bounds.py", "return 0", "return 1", lambda: False)
    assert row["honest"] is False
    assert "revert" in row["tx"]
    assert (ws / "bounds.py").read_text(encoding="utf-8") == task["source"]
    assert "span([1, 4, 2])" in (ws / "test_bounds.py").read_text(encoding="utf-8")
    (ws / "bounds.py").write_text("def span(nums):\n    return (max(nums) - min(nums)) if nums else 0\n", encoding="utf-8")
    fixed = subprocess.run([sys.executable, str(ws / "test_bounds.py")], cwd=str(ws), capture_output=True, text=True)
    assert fixed.returncode == 0


def test_failing_cases_do_not_contain_the_patch() -> None:
    from core.kernel.curriculum import diagnose

    sign = next(t for t in TASKS if t["id"] == "sign")
    note = diagnose(sign, sign["source"])
    assert "returned 1, expected -1" in note
    assert "sign(9) returned 1, expected 1" in note
    span = next(t for t in TASKS if t["id"] == "span")
    span_note = diagnose(span, span["source"])
    assert "span([1, 4, 2]) returned 0, expected 3" in span_note
    assert "max(nums)" not in span_note
    from core.kernel.curriculum import repair_note
    off = "def span(nums):\n    if not nums:\n        return 0\n    return max(nums) - min(nums) + 1\n"
    repair = repair_note(span, off)
    assert "returned 4, expected 3" in repair
    assert "max(nums)" not in repair
    assert "return -1" not in note
    assert sign["banned"] not in note
    for task in TASKS:
        assert checker_for(task["id"])(task["source"]) is False
    assert checker_for("clamp")("def clamp(n, lo, hi):\n    return min(max(n, lo), hi)\n") is True
    assert checker_for("sign")("def sign(n):\n    return (n > 0) - (n < 0)\n") is True
    assert checker_for("span")("def span(nums):\n    return (max(nums) - min(nums)) if nums else 0\n") is True

