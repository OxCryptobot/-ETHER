"""Unaided LIVE criteria: same rule as merge/ledger. Expansion fixtures inherit it."""
from __future__ import annotations

from core.loop.live_criteria import EXPAND, GATE, expansion_left, gate_met, unaided_pass


def test_p3_52_shape_passes() -> None:
    row = {
        "fixture": "ledger",
        "ok": True,
        "score": 1.0,
        "policy": "model",
        "tools": [
            "list_files",
            "bug_comments",
            "replace_once",
            "replace_once",
            "run_tests",
        ],
    }
    assert unaided_pass(row) is True


def test_playbook_does_not_count() -> None:
    row = {
        "ok": True,
        "score": 1.0,
        "policy": "teacher_playbook",
        "tools": ["bug_comments", "replace_once", "run_tests"],
    }
    assert unaided_pass(row) is False


def test_generate_without_replace_does_not_count() -> None:
    row = {
        "ok": True,
        "score": 1.0,
        "policy": "model",
        "tools": ["list_files", "run_tests"],
    }
    assert unaided_pass(row) is False


def test_gate_and_expansion() -> None:
    assert gate_met({"merge": 3, "ledger": 3}) is True
    assert gate_met({"merge": 2, "ledger": 3}) is False
    assert expansion_left(["merge", "ledger"]) == EXPAND
    assert GATE["merge"] == 3
