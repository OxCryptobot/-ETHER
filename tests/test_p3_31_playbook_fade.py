"""P3: skip LLM after takeover; comment-derived steps are craft_helper."""
from __future__ import annotations

import json
from pathlib import Path

from core.hard_live_playbook import (
    mutations_from_bug_comments,
    suggested_from_messages,
    wrap_live_decide,
)


def test_inner_not_called_after_takeover():
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
    calls_at_takeover = d.inner_calls()
    third = d([])
    fourth = d([])
    assert d.takeover() is True
    assert d.inner_calls() == calls_at_takeover
    assert third.get("tool") in {"replace_once", "anchor_edit", "run_tests"}
    assert fourth.get("tool") in {"replace_once", "anchor_edit", "run_tests", "done"}


def test_suggested_in_messages_sets_craft_helper():
    merge = (
        Path(__file__).resolve().parents[1] / "fixtures" / "repo_oracle_merge" / "merge.py"
    ).read_text(encoding="utf-8")
    sug = mutations_from_bug_comments("merge.py", merge)
    assert len(sug) >= 3

    def inner(_m):
        return {"tool": "list_files", "args": {}}

    d = wrap_live_decide("merge", inner)
    assert d([]).get("tool") == "list_files"
    obs = {
        "role": "user",
        "content": "Observation:\n" + json.dumps({"ok": True, "suggested": sug}) + "\nNext.",
    }
    # Second observe triggers takeover; suggested is already in the transcript.
    step = d(
        [
            {"role": "assistant", "content": json.dumps({"tool": "list_files", "args": {}})},
            obs,
        ]
    )
    assert step.get("tool") == "replace_once"
    assert d.policy() == "craft_helper"
    assert d.takeover() is True
    # I-005: further turns must not call inner.
    calls = d.inner_calls()
    d([obs])
    assert d.inner_calls() == calls


def test_suggested_from_messages_reads_latest_observation():
    payload = {
        "ok": True,
        "suggested": [
            {
                "tool": "replace_once",
                "args": {"path": "x.py", "old": "a", "new": "b"},
            }
        ],
    }
    messages = [
        {"role": "user", "content": "Observation:\n" + json.dumps(payload) + "\nNext."}
    ]
    got = suggested_from_messages(messages)
    assert got and got[0]["args"]["new"] == "b"
