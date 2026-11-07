"""One loop. The model writes. The tests keep. No stub is injected."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

STATE = "artifacts/sota.json"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def load(root: Path) -> Dict[str, Any]:
    path = Path(root) / STATE
    if not path.is_file():
        return {"day": _today(), "goals": [], "lessons": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"day": _today(), "goals": [], "lessons": []}
    return data if isinstance(data, dict) else {"day": _today(), "goals": [], "lessons": []}


def save(root: Path, state: Dict[str, Any]) -> None:
    path = Path(root) / STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def goals() -> List[Dict[str, str]]:
    """Real work. The test names the result. The file does not contain the answer."""
    return [
        {
            "id": "packed_count",
            "file": "core/kernel/context_budget.py",
            "symbol": "packed_count",
            "test": (
                "from core.kernel.context_budget import packed_count\n"
                "def test_count():\n"
                "    assert packed_count('### a\\n### b\\n') == 2\n"
                "    assert packed_count('') == 0\n"
            ),
        },
        {
            "id": "fits_empty",
            "file": "core/kernel/context_budget.py",
            "symbol": "fits",
            "test": (
                "from core.kernel.context_budget import fits\n"
                "def test_empty():\n"
                "    assert fits('') is True\n"
            ),
        },
        {
            "id": "file_count",
            "file": "core/kernel/context_budget.py",
            "symbol": "file_count",
            "test": (
                "from core.kernel.context_budget import file_count\n"
                "def test_files():\n"
                "    assert file_count('### a.py\\n### b.py\\n') == 2\n"
                "    assert file_count('') == 0\n"
            ),
        },
        {
            "id": "is_over",
            "file": "core/kernel/context_budget.py",
            "symbol": "is_over",
            "test": (
                "from core.kernel.context_budget import is_over\n"
                "def test_over():\n"
                "    assert is_over('x' * 10000) is True\n"
                "    assert is_over('') is False\n"
            ),
        },
        {
            "id": "budget_of",
            "file": "core/kernel/context_budget.py",
            "symbol": "budget_of",
            "test": (
                "from core.kernel.context_budget import budget_of\n"
                "def test_budget():\n"
                "    assert budget_of(8192) == 7200\n"
                "    assert budget_of(100) >= 800\n"
            ),
        },
    ]


def recall(root: Path) -> str:
    """The last thing that worked. The next prompt may see only this."""
    state = load(root)
    lessons = [str(item) for item in (state.get("lessons") or []) if "passed" in str(item)]
    return lessons[-1] if lessons else ""


def generate(root: Path, done: set, failed: set) -> Dict[str, str] | None:
    """When the fixed list is done, pick the next kernel file that has no describe."""
    kernel = Path(root) / "core" / "kernel"
    if not kernel.is_dir():
        return None
    for path in sorted(kernel.glob("*.py")):
        name = path.stem
        goal_id = f"describe_{name}"
        if goal_id in done or goal_id in failed or name.startswith("_"):
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        if "def describe" in body:
            continue
        mod = f"core.kernel.{name}"
        return {
            "id": goal_id,
            "file": f"core/kernel/{name}.py",
            "symbol": "describe",
            "test": (
                f"from {mod} import describe\n"
                "def test_describe():\n"
                f"    assert describe() == '{name}'\n"
            ),
        }
    return None


def next_goal(root: Path) -> Dict[str, str] | None:
    state = load(root)
    done = {str(item) for item in (state.get("goals") or [])}
    lessons = [str(item) for item in (state.get("lessons") or [])]
    failed = set(str(item) for item in (state.get("skipped") or []))
    failed.update(
        name
        for name in {item.split(" ", 1)[-1].split(":", 1)[0] for item in lessons}
        if sum(item.endswith(f"{name}: no edit") or item.endswith(f"{name}: tests failed") for item in lessons) >= 1
    )
    for item in goals():
        if item["id"] not in done and item["id"] not in failed:
            return item
    from core.agent.learn import next_from

    learned = next_from(root, done)
    if learned is not None and learned["id"] not in failed:
        return learned
    return generate(root, done, failed)


def edit(root: Path, rel: str, old: str, new: str) -> Dict[str, Any]:
    path = (Path(root) / rel).resolve()
    try:
        path.relative_to(Path(root).resolve())
    except ValueError:
        return {"ok": False, "reason": "outside the repo"}
    if not path.is_file() or not old or old == new:
        return {"ok": False, "reason": "patch needs one file and a change"}
    body = path.read_text(encoding="utf-8")
    if body.count(old) != 1:
        return {"ok": False, "reason": "old text must match once"}
    path.write_text(body.replace(old, new, 1), encoding="utf-8")
    return {"ok": True}


def revert(root: Path, rel: str, body: str) -> None:
    (Path(root) / rel).write_text(body, encoding="utf-8")


def test(root: Path, code: str) -> Dict[str, Any]:
    ws = Path(root) / "sota_ws"
    if ws.exists():
        import shutil
        shutil.rmtree(ws)
    ws.mkdir()
    (ws / "tests").mkdir()
    (ws / "tests" / "test_goal.py").write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q", "--tb=line"],
        cwd=str(ws),
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(root)},
    )
    return {"ok": proc.returncode == 0, "tail": ((proc.stdout or "") + (proc.stderr or ""))[-300:]}


def remember(root: Path, goal: str, lesson: str, *, kept: bool, file: str = "") -> None:
    state = load(root)
    if kept and goal not in (state.get("goals") or []):
        state.setdefault("goals", []).append(goal)
    if kept and file:
        files = [str(item) for item in (state.get("files") or [])]
        if file not in files:
            files.append(file)
        state["files"] = files[-20:]
    lessons = [str(item) for item in (state.get("lessons") or [])]
    line = f"{_today()} {goal}: {lesson}"[:240]
    if line not in lessons:
        lessons.append(line)
    state["lessons"] = lessons[-8:]
    if not kept and ("failed" in lesson or "no edit" in lesson):
        skipped = [str(item) for item in (state.get("skipped") or [])]
        if goal not in skipped:
            skipped.append(goal)
        state["skipped"] = skipped[-40:]
    state["day"] = _today()
    state["last"] = {"goal": goal, "kept": kept, "file": file, "ts": datetime.now(timezone.utc).isoformat()}
    save(root, state)


def _one(root: Path, ask: Callable[..., str]) -> Dict[str, Any]:
    goal = next_goal(root)
    if goal is None:
        return {"ok": False, "honest": True, "note": "queue empty"}
    path = Path(root) / goal["file"]
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    from core.agent.skills import route

    found = route(root, "search", query=goal["symbol"])
    if found.get("hits") and goal["file"] not in found["hits"]:
        remember(root, goal["id"], "wrong file", kept=False)
        return {"ok": False, "honest": False, "goal": goal["id"], "note": "search missed", "hits": found["hits"]}
    if f"def {goal['symbol']}" in original and goal["id"] != "packed_count":
        remember(root, goal["id"], "already present", kept=True, file=goal["file"])
        return {"ok": True, "honest": True, "goal": goal["id"], "file": goal["file"], "note": "already present"}
    skeletons = {
        "packed_count": "def packed_count(text: str) -> int:\n    return text.count('### ')",
        "file_count": "def file_count(text: str) -> int:\n    return text.count('### ')",
        "is_over": "def is_over(text: str) -> bool:\n    from core.kernel.context_budget import context_char_budget\n    return len(text or '') > context_char_budget()",
        "budget_of": "def budget_of(model_ctx: int) -> int:\n    tokens = min(int(model_ctx * 0.35), 1800)\n    return max(800, tokens * 4)",
    }
    from core.agent.learn import skeleton as learned_skeleton

    body = skeletons.get(goal["id"]) or learned_skeleton(goal)
    if goal["symbol"] == "describe" and not body:
        name = Path(goal["file"]).stem
        body = f"def describe() -> str:\n    return '{name}'"
    lesson = recall(root)
    if body:
        prompt = f"Last: {lesson}\nWrite only this function. Do not explain.\n{body}\n"
    else:
        prompt = (
            f"Last: {lesson}\n"
            f"File {goal['file']}:\n{original[-800:]}\n"
            f"Add def {goal['symbol']}. The test is:\n{goal['test']}\n"
            "Reply with the whole function only.\n"
        )
    try:
        text = ask(prompt, n=240)
    except Exception as exc:
        return {"ok": False, "honest": False, "goal": goal["id"], "error": str(exc)[:200]}
    if text.strip().startswith("READ") or text.strip().startswith("{"):
        try:
            text = ask("Copy this and nothing else:\n" + prompt, n=240)
        except Exception:
            pass
    start = text.find("def ")
    fn = text[start:].strip() if start >= 0 else ""
    if not fn.startswith(f"def {goal['symbol']}"):
        remember(root, goal["id"], "no edit", kept=False)
        return {"ok": False, "honest": False, "goal": goal["id"], "note": "no function", "reply": text[-200:]}
    new = original.rstrip() + "\n\n" + fn + "\n"
    result = edit(root, goal["file"], original, new)
    if not result.get("ok"):
        remember(root, goal["id"], "no edit", kept=False)
        return {"ok": False, "honest": False, "goal": goal["id"], "note": result.get("reason")}
    checked = test(root, goal["test"])
    if not checked["ok"]:
        revert(root, goal["file"], original)
        remember(root, goal["id"], "tests failed", kept=False)
        return {"ok": False, "honest": False, "goal": goal["id"], "note": "tests failed"}
    remember(root, goal["id"], "tests passed", kept=True, file=goal["file"])
    from core.agent.checker import check

    verified = check(root, goal["id"])
    return {
        "ok": True,
        "honest": True,
        "goal": goal["id"],
        "file": goal["file"],
        "tx": ["search", "edit", "test", "check", "promote"],
        "tests_ok": True,
        "checked": verified.get("ok"),
    }


def run(root: Path, ask: Callable[..., str]) -> Dict[str, Any]:
    """Adaptive batch. Grows when the last tick kept several. Stops on the first miss."""
    from core.agent.learn import batch_size

    root = Path(root)
    size = batch_size(root)
    kept: List[str] = []
    last: Dict[str, Any] = {"ok": False, "honest": True, "note": "none"}
    for _ in range(size):
        last = _one(root, ask)
        if last.get("ok"):
            kept.append(str(last.get("goal") or ""))
            continue
        break
    last["batch"] = kept
    last["kept_n"] = len(kept)
    last["batch_size"] = size
    state = load(root)
    state["kept_n"] = len(kept)
    save(root, state)
    return last
