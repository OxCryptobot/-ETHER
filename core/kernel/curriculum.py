"""One task at a time. The prompt never contains the answer."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _check_add(src: str) -> bool:
    ns: Dict[str, Any] = {}
    exec(src, ns)  # noqa: S102 — the model edit, already inside EditTx
    fn = ns.get("add")
    return callable(fn) and fn(2, 3) == 5 and fn(0, 0) == 0


def _check_clamp(src: str) -> bool:
    ns: Dict[str, Any] = {}
    exec(src, ns)  # noqa: S102
    fn = ns.get("clamp")
    return callable(fn) and fn(5, 0, 3) == 3 and fn(-1, 0, 3) == 0 and fn(2, 0, 3) == 2


def _check_sign(src: str) -> bool:
    ns: Dict[str, Any] = {}
    exec(src, ns)  # noqa: S102
    fn = ns.get("sign")
    return callable(fn) and fn(-4) == -1 and fn(0) == 0 and fn(9) == 1


def _check_span(src: str) -> bool:
    ns: Dict[str, Any] = {}
    exec(src, ns)  # noqa: S102
    fn = ns.get("span")
    if not callable(fn):
        return False
    try:
        return fn([1, 4, 2]) == 3 and fn([5]) == 0 and fn([]) == 0
    except Exception:
        return False


SPAN_TEST = (
    "from bounds import span\n"
    "assert span([1, 4, 2]) == 3\n"
    "assert span([5]) == 0\n"
    "assert span([]) == 0\n"
)


TASKS: List[Dict[str, Any]] = [
    {
        "id": "add",
        "file": "add.py",
        "source": "def add(a, b):\n    return a - b\n",
        "prompt": "add(2, 3) must be 5. Change only the broken return. Reply with exactly two lines:\nOLD: <the current line>\nNEW: <the fixed line>\n",
        "banned": "return a + b",
        "fn": "add",
        "cases": [((2, 3), 5), ((0, 0), 0)],
        "check": _check_add,
    },
    {
        "id": "clamp",
        "file": "clamp.py",
        "source": "def clamp(n, lo, hi):\n    return n\n",
        "prompt": "clamp(n, lo, hi) must keep n inside lo..hi. Change only the return. Reply with exactly two lines:\nOLD: <the current line>\nNEW: <the fixed line>\n",
        "banned": "min(",
        "fn": "clamp",
        "cases": [((5, 0, 3), 3), ((-1, 0, 3), 0), ((2, 0, 3), 2)],
        "check": _check_clamp,
    },
    {
        "id": "sign",
        "file": "sign.py",
        "source": "def sign(n):\n    return 1\n",
        "prompt": "sign(n) must be -1, 0, or 1. Change only the return. Reply with exactly two lines:\nOLD: <the current line>\nNEW: <the fixed line>\n",
        "banned": "return -1",
        "fn": "sign",
        "cases": [((-4,), -1), ((0,), 0), ((9,), 1)],
        "check": _check_sign,
    },
    {
        "id": "span",
        "file": "bounds.py",
        "source": "def span(nums):\n    return 0\n",
        "also": {"test_bounds.py": SPAN_TEST},
        "test": "test_bounds.py",
        "prompt": "test_bounds.py fails. Change only the return in bounds.py. Reply with exactly two lines:\nOLD: <the current line>\nNEW: <the fixed line>\n",
        "banned": "max(nums)",
        "check": _check_span,
    },
]


def diagnose(task: Dict[str, Any], src: str) -> str:
    """What the current code returns. Never the patch."""
    if task.get("test"):
        return "the test file failed"
    fn_name = str(task.get("fn") or "")
    cases = task.get("cases") or []
    if not fn_name or not cases:
        return ""
    ns: Dict[str, Any] = {}
    try:
        exec(src, ns)  # noqa: S102
        fn = ns.get(fn_name)
        if not callable(fn):
            return f"{fn_name} is missing"
        lines = []
        for args, want in cases:
            got = fn(*args)
            if got != want:
                shown = args[0] if len(args) == 1 else args
                lines.append(f"{fn_name}({shown}) returned {got}, expected {want}")
        return "; ".join(lines)[:300]
    except Exception:
        return "the function raised"


def _load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _passed(root: Path) -> List[str]:
    state = _load(root / "artifacts" / "curriculum.json")
    done = [str(x) for x in (state.get("passed") or [])]
    if done:
        return done
    hist = _load(root / "artifacts" / "honest_history.json")
    items = hist.get("items") or []
    if len(items) >= 2:
        return ["add"]
    return []


def next_task(root: Path) -> Optional[Dict[str, Any]]:
    done = set(_passed(root))
    for task in TASKS:
        if task["id"] not in done:
            return task
    return None


def mark_passed(root: Path, task_id: str) -> None:
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    done = _passed(root)
    if task_id not in done:
        done.append(task_id)
    path = art / "curriculum.json"
    path.write_text(json.dumps({"passed": done}, indent=2) + "\n", encoding="utf-8")


def checker_for(task_id: str) -> Callable[[str], bool]:
    for task in TASKS:
        if task["id"] == task_id:
            return task["check"]
    return lambda _src: False
