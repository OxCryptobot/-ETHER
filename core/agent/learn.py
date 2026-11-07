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
    return ""


def score(root: Path) -> Dict[str, Any]:
    """How far the loop has grown. Honest: only kept goals count."""
    have = kept(root)
    return {"kept": len(have), "goals": have, "learning": bool(have)}
