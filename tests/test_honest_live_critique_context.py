"""Phase-1 moves: honest rates, mandatory critique, context compress."""
from __future__ import annotations

from core.context import compress_text
from core.critique_on_fail import critique_fail, is_infra_fail
from core.honest_live import classify_row, compute_rates
from core.loop.handlers.tool_runtime_gate import is_honest_tool_path_pass


def test_honest_gate_still_rejects_generate():
    assert is_honest_tool_path_pass(
        {"ok": True, "strategy": "generate", "mode": "live", "degraded": []}
    ) is False
    assert is_honest_tool_path_pass(
        {"ok": True, "strategy": "tool_runtime", "mode": "live", "degraded": []}
    ) is True


def test_compute_rates_disguised_pass():
    rows = [
        {"ok": True, "strategy": "generate", "mode": "live", "degraded": []},
        {"ok": True, "strategy": "tool_runtime", "mode": "live", "degraded": []},
        {"ok": False, "strategy": "tool_runtime", "mode": "live", "degraded": ["timeout"]},
    ]
    rates = compute_rates(rows)
    assert rates["n_rows"] == 3
    assert rates["disguised_pass_n"] == 1
    assert rates["live_honest_n"] == 1
    assert rates["soft_launch_blocked"] is True
    assert classify_row(rows[0])["disguised_pass"] is True


def test_infra_skip_and_critique_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    # re-import roots would still use module-level ROOT; call is_infra only
    assert is_infra_fail(failure_type="infra", stderr="") is True
    assert is_infra_fail(
        failure_type="timeout", stderr="cannot connect to the docker daemon"
    ) is True
    assert is_infra_fail(failure_type="no_progress", stderr="AssertionError") is False

    art = critique_fail(
        job_id="unit_fail_1",
        failure_type="no_progress",
        note="unit test fail",
        code="def solve():\n    return 1\n",
        enqueue=False,
    )
    assert art.get("skipped") is not True
    assert art.get("mandatory") is True
    assert "next_hypothesis" in art
    assert art.get("labradorite_ok") in (True, False)


def test_compress_respects_budget_and_query():
    blob = ("alpha beta gamma\n\n" * 50) + ("tool_runtime apply_patch\n\n" * 20)
    out = compress_text(blob, query="tool_runtime apply_patch", max_chars=400)
    assert len(out) <= 400
    assert "tool_runtime" in out or "apply_patch" in out
