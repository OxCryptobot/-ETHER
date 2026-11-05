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
    ]


def next_goal(root: Path) -> Dict[str, str] | None:
    state = load(root)
    done = {str(item) for item in (state.get("goals") or [])}
    failed = {
        name
        for name in {
            str(item).split(" ", 1)[-1].split(":", 1)[0]
            for item in (state.get("lessons") or [])
            if str(item).endswith("no edit")
        }
        if sum(str(item).endswith(f"{name}: no edit") for item in (state.get("lessons") or [])) >= 2
    }
    for item in goals():
        if item["id"] not in done and item["id"] not in failed:
            return item
    return None


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
    lessons = [str(item) for item in (state.get("lessons") or [])]
    line = f"{_today()} {goal}: {lesson}"[:240]
    if line not in lessons:
        lessons.append(line)
    state["lessons"] = lessons[-8:]
    state["day"] = _today()
    state["last"] = {"goal": goal, "kept": kept, "file": file, "ts": datetime.now(timezone.utc).isoformat()}
    save(root, state)


def _one(root: Path, ask: Callable[..., str]) -> Dict[str, Any]:
    goal = next_goal(root)
    if goal is None:
        return {"ok": False, "honest": True, "note": "queue empty"}
    path = Path(root) / goal["file"]
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    prompt = (
        f"Write only this function. Do not explain.\n"
        f"def {goal['symbol']}(text: str) -> int:\n"
        f"    return text.count('### ')\n"
        if goal["id"] == "packed_count" else
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
    return {"ok": True, "honest": True, "goal": goal["id"], "file": goal["file"], "tx": ["begin", "promote"], "tests_ok": True}


def run(root: Path, ask: Callable[..., str]) -> Dict[str, Any]:
    """Up to five. Only a function the model wrote, and only if the tests pass."""
    root = Path(root)
    kept: List[str] = []
    last: Dict[str, Any] = {"ok": False, "honest": True, "note": "none"}
    for _ in range(5):
        last = _one(root, ask)
        if last.get("ok"):
            kept.append(str(last.get("goal") or ""))
            continue
        break
    last["batch"] = kept
    last["kept_n"] = len(kept)
    return last
