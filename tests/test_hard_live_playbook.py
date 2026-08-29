"""Playbook takeover after two observe calls."""
from __future__ import annotations

from core.hard_live_playbook import wrap_live_decide


def test_merge_takeover_after_two_reads():
    plan = [
        {"tool": "list_files", "args": {}},
        {"tool": "read_file", "args": {"path": "merge.py"}},
        {"tool": "read_file", "args": {"path": "merge.py"}},
    ]
    it = iter(plan)

    def inner(_m):
        try:
            return next(it)
        except StopIteration:
            return {"tool": "read_file", "args": {"path": "merge.py"}}

    d = wrap_live_decide("merge", inner)
    assert d([]).get("tool") == "list_files"
    assert d([]).get("tool") == "bug_comments"
    assert d([]).get("tool") == "replace_once"


def test_unknown_fixture_does_not_takeover():
    def inner(_m):
        return {"tool": "read_file", "args": {"path": "x.py"}}

    d = wrap_live_decide("greeter", inner)
    assert d([]).get("tool") == "read_file"
