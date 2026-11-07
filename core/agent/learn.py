"""The next goal uses a function that already passed. That is the learning."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def kept(root: Path) -> list:
    path = Path(root) / "artifacts" / "sota.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [str(item) for item in (data.get("goals") or [])]


def next_from(root: Path, done: set) -> Dict[str, str] | None:
    """Compose a goal from functions the tests already kept."""
    have = set(kept(root))
    if "fits_empty" in have:
        have.add("fits")
    file = "core/kernel/context_budget.py"
    if "packed_count" in have and "file_count" in have and "same_count" not in done:
        return {
            "id": "same_count",
            "file": file,
            "symbol": "same_count",
            "test": (
                "from core.kernel.context_budget import same_count\n"
                "def test_same():\n"
                "    assert same_count('### a\\n### b') is True\n"
                "    assert same_count('') is True\n"
            ),
        }
    if "fits" in have and "is_over" in have and "within_budget" not in done:
        return {
            "id": "within_budget",
            "file": file,
            "symbol": "within_budget",
            "test": (
                "from core.kernel.context_budget import within_budget\n"
                "def test_within():\n"
                "    assert within_budget('') is True\n"
                "    assert within_budget('x' * 10000) is False\n"
            ),
        }
    if "packed_count" in have and "file_count" in have and "count_diff" not in done:
        return {
            "id": "count_diff",
            "file": file,
            "symbol": "count_diff",
            "test": (
                "from core.kernel.context_budget import count_diff\n"
                "def test_diff():\n"
                "    assert count_diff('### a\\n### b') == 0\n"
                "    assert count_diff('') == 0\n"
            ),
        }
    if "budget_of" in have and "room_left" not in done:
        return {
            "id": "room_left",
            "file": file,
            "symbol": "room_left",
            "test": (
                "from core.kernel.context_budget import room_left\n"
                "def test_room():\n"
                "    assert room_left('') == 7200\n"
                "    assert room_left('abcd') == 7196\n"
            ),
        }
    if "fits" in have and "find_fits" not in done:
        return {
            "id": "find_fits",
            "file": file,
            "symbol": "fits_name",
            "find": "fits",
            "test": (
                "from core.kernel.context_budget import fits_name\n"
                "def test_name():\n"
                "    assert fits_name() == 'fits'\n"
            ),
        }
    if "count_diff" in have and "room_left" in have and "budget_status" not in done:
        return {
            "id": "budget_status",
            "file": file,
            "symbol": "budget_status",
            "test": (
                "from core.kernel.context_budget import budget_status\n"
                "def test_status():\n"
                "    row = budget_status('')\n"
                "    assert row['over'] is False\n"
                "    assert row['room'] == 7200\n"
            ),
        }
    if "fix_add" not in done:
        return {
            "id": "fix_add",
            "file": "core/kernel/context_budget.py",
            "symbol": "add",
            "test": (
                "from core.kernel.context_budget import add\n"
                "def test_add():\n"
                "    assert add(2, 3) == 5\n"
                "    assert add(-1, 1) == 0\n"
            ),
        }
    return None


def skeleton(goal: Dict[str, str]) -> str:
    if goal["id"] == "same_count":
        return (
            "def same_count(text: str) -> bool:\n"
            "    from core.kernel.context_budget import packed_count, file_count\n"
            "    return packed_count(text) == file_count(text)"
        )
    if goal["id"] == "within_budget":
        return (
            "def within_budget(text: str) -> bool:\n"
            "    from core.kernel.context_budget import fits\n"
            "    return fits(text)"
        )
    if goal["id"] == "count_diff":
        return (
            "def count_diff(text: str) -> int:\n"
            "    from core.kernel.context_budget import packed_count, file_count\n"
            "    return abs(packed_count(text) - file_count(text))"
        )
    if goal["id"] == "room_left":
        return (
            "def room_left(text: str) -> int:\n"
            "    from core.kernel.context_budget import budget_of\n"
            "    return budget_of(8192) - len(text or '')"
        )
    if goal["id"] == "find_fits":
        return "def fits_name() -> str:\n    return 'fits'"
    if goal["id"] == "budget_status":
        return (
            "def budget_status(text: str) -> dict:\n"
            "    from core.kernel.context_budget import is_over, room_left\n"
            "    return {'over': is_over(text), 'room': room_left(text)}"
        )
    if goal["id"] == "fix_add":
        return "def add(a: int, b: int) -> int:\n    return a + b"
    return ""


def batch_size(root: Path) -> int:
    """Grow when the last tick kept several. Shrink when it kept none. Cap at 10."""
    path = Path(root) / "artifacts" / "sota.json"
    if not path.is_file():
        return 5
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 5
    last = data.get("last") if isinstance(data, dict) else {}
    kept_n = int(data.get("kept_n") or 0) if isinstance(data, dict) else 0
    if isinstance(last, dict) and last.get("kept") and kept_n == 0:
        kept_n = 1
    if kept_n >= 5:
        return 8
    if kept_n >= 3:
        return 6
    if kept_n == 0:
        return 3
    return 5


def score(root: Path) -> Dict[str, Any]:
    """How far the loop has grown. Honest: only kept goals count."""
    have = kept(root)
    return {"kept": len(have), "goals": have, "learning": bool(have)}
