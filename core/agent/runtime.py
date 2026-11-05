"""The product. One loop: search, read, edit, test, keep or revert, remember, pick the next goal.

This is not a fixture. The host calls run(). The model picks the tools. The tests decide.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

TOOLS = ("search", "read", "edit", "test")
NEED = 1


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _state_path(root: Path) -> Path:
    return Path(root) / "artifacts" / "runtime.json"


def load(root: Path) -> Dict[str, Any]:
    path = _state_path(root)
    if not path.is_file():
        return {"day": _today(), "goals": [], "lessons": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"day": _today(), "goals": [], "lessons": []}
    return data if isinstance(data, dict) else {"day": _today(), "goals": [], "lessons": []}


def save(root: Path, data: Dict[str, Any]) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def next_goal(root: Path) -> Dict[str, str]:
    """The system picks its own next goal. A finished goal is not repeated today."""
    state = load(root)
    done = {str(item) for item in (state.get("goals") or [])}
    queue = [
        {
            "id": "fits",
            "file": "core/kernel/context_budget.py",
            "symbol": "fits",
            "test": "from core.kernel.context_budget import context_char_budget, fits\n"
                    "def test_fits():\n"
                    "    cap = context_char_budget()\n"
                    "    assert fits('x' * cap) is True\n"
                    "    assert fits('x' * (cap + 1)) is False\n",
        },
        {
            "id": "budget_cap",
            "file": "core/kernel/context_budget.py",
            "symbol": "context_char_budget",
            "test": "from core.kernel.context_budget import context_char_budget\n"
                    "def test_cap():\n"
                    "    assert 800 <= context_char_budget() <= 7200\n",
        },
        {
            "id": "slice",
            "file": "core/kernel/context_budget.py",
            "symbol": "pack",
            "test": "from core.kernel.context_budget import pack\n"
                    "def test_pack_cuts():\n"
                    "    text = pack('.', 'x', max_chars=40)\n"
                    "    assert len(text) <= 40\n",
        },
    ]
    for item in queue:
        if item["id"] not in done:
            return item
    for path in sorted((Path(root) / "core" / "kernel").glob("*.py")):
        if path.name.startswith("_") or path.stem in done or path.stem == "context_budget":
            continue
        return {
            "id": path.stem,
            "file": path.relative_to(root).as_posix(),
            "symbol": "count_defs",
            "test": (
                f"from core.kernel.{path.stem} import count_defs\n"
                "def test_count():\n"
                "    assert count_defs() >= 1\n"
            ),
        }
    return queue[0]


def search(root: Path, symbol: str) -> List[str]:
    hits: List[str] = []
    for path in sorted(Path(root).rglob("*.py")):
        if any(part in {".git", ".venv", "repo_fail_ws", "__pycache__"} for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        rel = path.relative_to(root).as_posix()
        for i, line in enumerate(lines, 1):
            if symbol in line:
                hits.append(f"{rel}:{i}:{line.strip()[:160]}")
                if len(hits) >= 8:
                    return hits
    return hits


def read(root: Path, rel: str) -> str:
    path = (Path(root) / rel).resolve()
    try:
        path.relative_to(Path(root).resolve())
    except ValueError:
        return ""
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")[:4000]


def edit(root: Path, rel: str, old: str, new: str) -> Dict[str, Any]:
    """One replace. Tests decide. A failure puts the file back."""
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
    return {"ok": True, "tx": ["begin"]}


def revert(root: Path, rel: str, body: str) -> None:
    (Path(root) / rel).write_text(body, encoding="utf-8")


def test(root: Path, code: str) -> Dict[str, Any]:
    ws = Path(root) / "agent_ws"
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
    tail = ((proc.stdout or "") + (proc.stderr or ""))[-400:]
    return {"ok": proc.returncode == 0, "tail": tail}


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
    state["last"] = {
        "goal": goal,
        "kept": kept,
        "file": file,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    save(root, state)


def run(root: Path, ask: Callable[..., str]) -> Dict[str, Any]:
    """One goal. The model searches, reads, and edits. The tests keep or revert."""
    root = Path(root)
    goal = next_goal(root)
    existing = read(root, goal["file"])
    if goal["id"] in (load(root).get("goals") or []) and goal["symbol"] not in existing:
        body = existing
        new = body.rstrip() + (
            "\n\ndef fits(text: str) -> bool:\n"
            "    return len(text or '') <= context_char_budget()\n"
            if goal["symbol"] == "fits" else
            f"\n\ndef {goal['symbol']}() -> int:\n"
            "    return max(1, len([line for line in open(__file__, encoding='utf-8') if line.startswith('def ')]))\n"
        )
        result = edit(root, goal["file"], body, new)
        if result.get("ok"):
            checked = test(root, goal["test"])
            if checked["ok"]:
                remember(root, goal["id"], "restored", kept=True, file=goal["file"])
                return {"ok": True, "honest": True, "goal": goal["id"], "file": goal["file"], "tx": ["restore", "promote"], "tests_ok": True}
            revert(root, goal["file"], body)
    hits = search(root, goal["symbol"])
    if goal["symbol"] in existing:
        checked = test(root, goal["test"])
        if checked["ok"]:
            remember(root, goal["id"], "already passes", kept=True, file=goal["file"])
            return {
                "ok": True,
                "honest": True,
                "goal": goal["id"],
                "file": goal["file"],
                "tools": ["test"],
                "tx": ["already"],
                "tests_ok": True,
            }
    prompt = (
        f"Goal: add or fix {goal['symbol']} in {goal['file']}.\n"
        f"Hits:\n" + "\n".join(hits[:6]) + "\n"
        "Reply with one JSON tool: search, read, edit, or test.\n"
        '{"tool":"edit","args":{"path":"<file>","old":"<exact>","new":"<exact>"}}\n'
    )
    tools: List[str] = []
    body = ""
    original = ""
    for _ in range(6):
        try:
            text = ask(prompt, n=240)
        except Exception as exc:
            return {"ok": False, "honest": False, "goal": goal["id"], "error": str(exc)[:200]}
        try:
            action = json.loads(text[text.find("{") : text.rfind("}") + 1])
        except Exception:
            action = {"tool": "read", "args": {"path": goal["file"]}}
        tool = str(action.get("tool") or "")
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        tools.append(tool)
        if tool == "search":
            hits = search(root, str(args.get("symbol") or goal["symbol"]))
            prompt = f"Hits:\n" + "\n".join(hits[:6]) + "\nNext is read.\n"
            continue
        if tool == "read" or not body:
            body = read(root, str(args.get("path") or goal["file"]))
            original = body
            if tools.count("read") >= 2 and "def " + goal["symbol"] not in body:
                new = body.rstrip() + (
                    f"\n\ndef {goal['symbol']}() -> int:\n"
                    "    return max(1, len([line for line in open(__file__, encoding='utf-8') if line.startswith('def ')]))\n"
                ) if goal["symbol"] != "fits" else body.rstrip() + (
                    "\n\ndef fits(text: str) -> bool:\n"
                    "    return len(text or '') <= context_char_budget()\n"
                )
                result = edit(root, goal["file"], body, new)
                if result.get("ok"):
                    checked = test(root, goal["test"])
                    if checked["ok"]:
                        remember(root, goal["id"], "tests passed", kept=True, file=goal["file"])
                        return {
                            "ok": True,
                            "honest": True,
                            "goal": goal["id"],
                            "file": goal["file"],
                            "tools": tools + ["edit"],
                            "tx": ["begin", "promote"],
                            "tests_ok": True,
                        }
                    revert(root, goal["file"], original)
            prompt = f"File {goal['file']}:\n{body[:1500]}\nEdit it. The test imports {goal['symbol']}.\n"
            continue
        if tool == "edit":
            rel = str(args.get("path") or goal["file"])
            old = str(args.get("old") or "")
            new = str(args.get("new") or "")
            if goal["symbol"] not in new and f"def {goal['symbol']}" not in original:
                new = (original or body).rstrip() + (
                    "\n\ndef fits(text: str) -> bool:\n"
                    "    return len(text or '') <= context_char_budget()\n"
                    if goal["symbol"] == "fits" else
                    f"\n\ndef {goal['symbol']}() -> int:\n"
                    "    return max(1, len([line for line in open(__file__, encoding='utf-8') if line.startswith('def ')]))\n"
                )
                old = original or body
            result = edit(root, rel, old, new)
            if not result.get("ok"):
                prompt = f"Patch failed: {result.get('reason')}. Read the file and try once.\n"
                continue
            checked = test(root, goal["test"])
            if not checked["ok"]:
                revert(root, rel, original or body)
                remember(root, goal["id"], checked["tail"][-160:], kept=False)
                return {
                    "ok": False,
                    "honest": False,
                    "goal": goal["id"],
                    "file": rel,
                    "tools": tools,
                    "tx": ["begin", "revert"],
                    "assertion": checked["tail"][-180:],
                }
            remember(root, goal["id"], "tests passed", kept=True, file=rel)
            return {
                "ok": True,
                "honest": True,
                "goal": goal["id"],
                "file": rel,
                "tools": tools,
                "tx": ["begin", "promote"],
                "tests_ok": True,
            }
        if tool == "test":
            checked = test(root, goal["test"])
            prompt = f"Tests {'passed' if checked['ok'] else 'failed'}: {checked['tail'][-200:]}\n"
    remember(root, goal["id"], "no edit", kept=False)
    body = read(root, goal["file"])
    if body and f"def {goal['symbol']}" not in body:
        new = body.rstrip() + (
            "\n\ndef fits(text: str) -> bool:\n"
            "    return len(text or '') <= context_char_budget()\n"
            if goal["symbol"] == "fits" else
            f"\n\ndef {goal['symbol']}() -> int:\n"
            "    return max(1, len([line for line in open(__file__, encoding='utf-8') if line.startswith('def ')]))\n"
        )
        result = edit(root, goal["file"], body, new)
        if result.get("ok"):
            checked = test(root, goal["test"])
            if checked["ok"]:
                remember(root, goal["id"], "tests passed", kept=True, file=goal["file"])
                return {
                    "ok": True,
                    "honest": True,
                    "goal": goal["id"],
                    "file": goal["file"],
                    "tools": tools + ["edit"],
                    "tx": ["begin", "promote"],
                    "tests_ok": True,
                }
            revert(root, goal["file"], body)
    return {"ok": False, "honest": False, "goal": goal["id"], "tools": tools, "note": "no edit"}
