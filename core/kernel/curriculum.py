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


def _check_above(src: str) -> bool:
    ns: Dict[str, Any] = {}
    exec(src, ns)  # noqa: S102
    fn = ns.get("above")
    if not callable(fn):
        return False
    try:
        return fn([1, 5, 3], 3) == 1 and fn([], 0) == 0 and fn([2, 2], 1) == 2
    except Exception:
        return False


def _check_uniq(src: str) -> bool:
    ns: Dict[str, Any] = {}
    exec(src, ns)  # noqa: S102
    fn = ns.get("uniq")
    if not callable(fn):
        return False
    try:
        return fn([1, 1, 2, 1]) == [1, 2] and fn([]) == [] and fn([3, 3]) == [3]
    except Exception:
        return False


UNIQ_TEST = (
    "from uniq import uniq\n"
    "assert uniq([1, 1, 2, 1]) == [1, 2]\n"
    "assert uniq([]) == []\n"
    "assert uniq([3, 3]) == [3]\n"
)

SPAN_TEST = (
    "from bounds import span\n"
    "assert span([1, 4, 2]) == 3\n"
    "assert span([5]) == 0\n"
    "assert span([]) == 0\n"
)

MERGE_SRC = (
    "def merge_intervals(intervals):\n"
    "    if not intervals:\n"
    "        return []\n"
    "    out = []\n"
    "    for start, end in intervals:\n"
    "        if not out:\n"
    "            out.append((start, end))\n"
    "            continue\n"
    "        ps, pe = out[-1]\n"
    "        if start <= pe and end <= pe:\n"
    "            continue\n"
    "        out.append((start, end))\n"
    "    return out\n"
)

MERGE_TEST = (
    "import sys\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
    "from intervals import merge_intervals\n"
    "assert merge_intervals([]) == []\n"
    "assert merge_intervals([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]\n"
    "assert merge_intervals([(1, 3), (2, 5)]) == [(1, 5)]\n"
)


def _check_pair(src: str) -> bool:
    greet_src = src.split("def greet", 1)[-1] if "def greet" in src else ""
    if "person(" not in greet_src:
        return False
    ns: Dict[str, Any] = {}
    exec(src, ns)  # noqa: S102
    person = ns.get("person")
    greet = ns.get("greet")
    if not callable(person) or not callable(greet):
        return False
    try:
        return person() == "ada" and greet() == "hi ada"
    except Exception:
        return False


def _check_ends(src: str) -> bool:
    ns: Dict[str, Any] = {}
    exec(src, ns)  # noqa: S102
    fn = ns.get("ends")
    if not callable(fn):
        return False
    try:
        return fn("ether") == "er" and fn("a") == "a" and fn("") == ""
    except Exception:
        return False


def _check_merge(src: str) -> bool:
    ns: Dict[str, Any] = {}
    exec(src, ns)  # noqa: S102
    fn = ns.get("merge_intervals")
    if not callable(fn):
        return False
    try:
        return (
            fn([]) == []
            and fn([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]
            and fn([(1, 3), (2, 5)]) == [(1, 5)]
        )
    except Exception:
        return False


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
        "fn": "span",
        "cases": [(([1, 4, 2],), 3), (([5],), 0), (([],), 0)],
        "prompt": "test_bounds.py fails. Reply with a complete def span function, or exactly two lines:\nOLD: <the current line>\nNEW: <the fixed line>\n",
        "banned": "max(nums)",
        "check": _check_span,
    },
    {
        "id": "uniq",
        "file": "uniq.py",
        "source": "def uniq(nums):\n    return list(nums)\n",
        "also": {"test_uniq.py": UNIQ_TEST},
        "test": "test_uniq.py",
        "fn": "uniq",
        "cases": [(([1, 1, 2, 1],), [1, 2]), (([],), []), (([3, 3],), [3])],
        "prompt": "test_uniq.py fails. Keep the first time each value appears, in that order. Reply with a complete def uniq function.\n",
        "banned": "dict.fromkeys",
        "check": _check_uniq,
    },
    {
        "id": "above",
        "file": "above.py",
        "source": "def above(nums, limit):\n    return len(nums)\n",
        "fn": "above",
        "cases": [(([1, 5, 3], 3), 1), (([], 0), 0), (([2, 2], 1), 2)],
        "prompt": "above(nums, limit) counts values strictly greater than limit. Reply with a complete def above function.\n",
        "banned": "n > limit",
        "check": _check_above,
    },
    {
        "id": "merge",
        "file": "intervals.py",
        "source": MERGE_SRC,
        "also": {"tests/test_merge.py": MERGE_TEST},
        "test": "tests/test_merge.py",
        "repo": True,
        "budget": 1600,
        "predict": 320,
        "fn": "merge_intervals",
        "cases": [
            (([(1, 3), (2, 5)],), [(1, 5)]),
            (([(1, 2), (4, 5)],), [(1, 2), (4, 5)]),
            (([],), []),
        ],
        "prompt": "tests/test_merge.py fails. Overlapping intervals must become one range. Reply with a complete def merge_intervals function.\n",
        "banned": "max(pe, end)",
        "check": _check_merge,
    },
    {
        "id": "ends",
        "file": "ends.py",
        "source": "def ends(s):\n    return s[0] if s else \"\"\n",
        "also": {
            "tests/test_ends.py": (
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
                "from ends import ends\n"
                "assert ends('ether') == 'er'\n"
                "assert ends('a') == 'a'\n"
                "assert ends('') == ''\n"
            )
        },
        "test": "tests/test_ends.py",
        "repo": True,
        "must_read": True,
        "budget": 1200,
        "predict": 160,
        "fn": "ends",
        "cases": [(("ether",), "er"), (("a",), "a"), (("",), "")],
        "prompt": "Reply with a complete def ends function. First and last character, or empty.\n",
        "banned": "s[-1]",
        "check": _check_ends,
    },
    {
        "id": "pair",
        "file": "greet.py",
        "source": "def greet():\n    return 'hi'\n",
        "also": {
            "person.py": "def person():\n    return ''\n",
            "tests/test_pair.py": (
                "import inspect\n"
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
                "from person import person\n"
                "from greet import greet\n"
                "assert person() == 'ada'\n"
                "assert 'person(' in inspect.getsource(greet)\n"
                "assert greet() == 'hi ada'\n"
            ),
        },
        "parts": {"person": "person.py", "greet": "greet.py"},
        "test": "tests/test_pair.py",
        "repo": True,
        "must_read": True,
        "budget": 1600,
        "predict": 220,
        "fn": "greet",
        "prompt": "Reply with a complete def person and a complete def greet. greet must call person.\n",
        "banned": "return 'ada'",
        "check": _check_pair,
    },
]


def write_task(workspace: Path, task: Dict[str, Any]) -> None:
    dest = workspace / task["file"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(task["source"], encoding="utf-8")
    for name, body in (task.get("also") or {}).items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def diagnose(task: Dict[str, Any], src: str) -> str:
    """What the current code returns. Never the patch."""
    fn_name = str(task.get("fn") or "")
    cases = task.get("cases") or []
    if not fn_name or not cases:
        return "the test file failed" if task.get("test") else ""
    ns: Dict[str, Any] = {}
    try:
        exec(src, ns)  # noqa: S102
        fn = ns.get(fn_name)
        if not callable(fn):
            return f"{fn_name} is missing"
        lines = []
        for args, want in cases:
            got = fn(*args)
            shown = args[0] if len(args) == 1 else args
            lines.append(f"{fn_name}({shown}) returned {got}, expected {want}")
        return "; ".join(lines)[:400]
    except Exception:
        return "the function raised"


def repair_note(task: Dict[str, Any], attempted_src: str) -> str:
    note = diagnose(task, attempted_src)
    if not note or task.get("banned") and task["banned"] in note:
        return ""
    return note


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


def kept(root: Path, task: Dict[str, Any]) -> bool:
    from core.kernel.worktree import tree_path

    ws = tree_path(root)
    try:
        if task.get("parts"):
            blobs = []
            for rel in task["parts"].values():
                path = ws / str(rel)
                if not path.is_file():
                    return False
                blobs.append(path.read_text(encoding="utf-8"))
            return bool(task["check"]("\n".join(blobs)))
        path = ws / str(task["file"])
        if not path.is_file():
            return False
        return bool(task["check"](path.read_text(encoding="utf-8")))
    except Exception:
        return False


def hold_status(root: Path) -> Dict[str, Any]:
    done = set(_passed(root))
    repo_tasks = [task for task in TASKS if task.get("repo") and task["id"] in done]
    if not repo_tasks:
        return {"note": "curriculum_hold", "persisted": False}
    missing = [task for task in repo_tasks if not kept(root, task)]
    if missing:
        return {"note": "curriculum_hold", "persisted": False, "task": missing[0]["id"], "file": missing[0]["file"]}
    last = repo_tasks[-1]
    return {"note": "kept", "persisted": True, "task": last["id"], "file": last["file"]}


def next_task(root: Path) -> Optional[Dict[str, Any]]:
    done = set(_passed(root))
    for task in TASKS:
        if task["id"] not in done:
            return task
    for task in TASKS:
        if task.get("repo") and task["id"] in done and not kept(root, task):
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
