"""FAST p3_41: unaided wrap never hands merge to the teacher book."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MOD = Path(__file__).resolve().parents[1] / "core" / "hard_live_playbook.py"
_SPEC = importlib.util.spec_from_file_location("ether_hard_live_playbook", _MOD)
assert _SPEC and _SPEC.loader
playbook = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(playbook)
wrap_live_decide = playbook.wrap_live_decide


def test_unaided_never_emits_teacher_book() -> None:
    calls: list[int] = []

    def inner(_m: object) -> dict:
        calls.append(1)
        return {"tool": "list_files", "args": {}}

    decide = wrap_live_decide("merge", inner, allow_takeover=False)
    for _ in range(5):
        assert decide([]).get("tool") == "list_files"
    assert decide.policy() == "model"  # type: ignore[attr-defined]
    assert decide.takeover() is False  # type: ignore[attr-defined]
    assert len(calls) == 5


def test_default_wrap_still_takes_over() -> None:
    plan = [
        {"tool": "list_files", "args": {}},
        {"tool": "read_file", "args": {"path": "merge.py"}},
        {"tool": "read_file", "args": {"path": "merge.py"}},
    ]
    it = iter(plan)

    def inner(_m: object) -> dict:
        try:
            return next(it)
        except StopIteration:
            return {"tool": "read_file", "args": {"path": "merge.py"}}

    decide = wrap_live_decide("merge", inner)
    assert decide([]).get("tool") == "list_files"
    assert decide([]).get("tool") == "bug_comments"
    assert decide.takeover() is True  # type: ignore[attr-defined]
