"""P3: playbook takeover is labeled teacher_playbook. BUG comments become replace_once."""
from __future__ import annotations

from pathlib import Path

from core.hard_live_playbook import mutations_from_bug_comments, wrap_live_decide


def test_takeover_sets_teacher_policy():
    plan = [
        {"tool": "list_files", "args": {}},
        {"tool": "read_file", "args": {"path": "merge.py"}},
    ]
    it = iter(plan)

    def inner(_m):
        try:
            return next(it)
        except StopIteration:
            return {"tool": "read_file", "args": {"path": "merge.py"}}

    d = wrap_live_decide("merge", inner)
    assert d.policy() == "model"
    assert d([]).get("tool") == "list_files"
    assert d([]).get("tool") == "bug_comments"
    assert d.policy() == "teacher_playbook"
    assert d.takeover() is True


def test_mutations_from_merge_bug_comments():
    src = (Path(__file__).resolve().parents[1] / "fixtures" / "repo_oracle_merge" / "merge.py").read_text(
        encoding="utf-8"
    )
    steps = mutations_from_bug_comments("merge.py", src)
    olds = [s["args"]["old"] for s in steps]
    news = [s["args"]["new"] for s in steps]
    assert any("return list(b)" in n for n in news)
    assert any("return list(a)" in n for n in news)
    assert any("return b  # BUG" in o for o in olds)
    # remainder is now a `# BUG: should also` comment — craft, not a fixture dict
    assert any("out.extend(b[j:])" in n for n in news)
