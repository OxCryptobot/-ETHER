"""Batch 10 item 5d: real vs planted keeps and a filler rate over real keeps only."""
from __future__ import annotations

import json

from core.agent import outcome


def _write(root, rows):
    path = outcome.traj_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_real_and_planted_keeps_are_split(tmp_path) -> None:
    rows = [
        {"kind": "pass", "tests_ok": True, "regressions": 0, "goal_kind": "fix_test", "goal": "fix_test_a", "via": "sbfl"},
        {"kind": "fail", "goal_kind": "fix_test", "goal": "fix_test_b", "via": "test_import"},
        {"kind": "pass", "tests_ok": True, "regressions": 0, "goal_kind": "fix_test", "goal": "planted_x", "via": "planted"},
        {"kind": "pass", "tests_ok": True, "regressions": 0, "goal_kind": "fix_test", "goal": "planted_y", "planted": True},
        {"kind": "fail", "goal_kind": "fix_test", "goal": "planted_z", "via": "planted"},
        {"kind": "pass", "tests_ok": True, "goal_kind": "legacy", "goal": "describe_agent"},  # legacy filler keep
    ]
    _write(tmp_path, rows)
    m = outcome.metrics(tmp_path)
    assert m["real_attempts"] == 2 and m["real_kept"] == 1
    assert m["planted_attempts"] == 3 and m["planted_kept"] == 2
    assert m["filler_rate_real"] == 0.0 and m["filler_rate"] > 0  # legacy filler no longer pollutes the real rate
    doc = outcome.summary_doc(tmp_path)
    assert doc["metrics"]["real_kept"] == 1 and doc["metrics"]["planted_kept"] == 2


def test_filler_rate_real_counts_real_filler_keeps(tmp_path) -> None:
    from core.agent.goal_quality import FILLER_IDS

    fid = sorted(FILLER_IDS)[0]
    rows = [{"kind": "pass", "tests_ok": True, "regressions": 0, "goal_kind": "fix_test", "goal": fid},
            {"kind": "pass", "tests_ok": True, "regressions": 0, "goal_kind": "fix_test", "goal": "fix_test_ok"}]
    _write(tmp_path, rows)
    assert outcome.metrics(tmp_path)["filler_rate_real"] == 0.5
