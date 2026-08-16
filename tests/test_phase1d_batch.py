"""Phase 1D batch — status, smoothness honesty, whats_next blockers."""
from __future__ import annotations


def test_phase1d_status_runs():
    from core.phase1d_status import compute

    p = compute()
    assert p["phase"] == "1D"
    assert p["training_wheels"] is True
    assert p["soft_launch"] is False
    assert p["checks_n"] >= 4
    assert p.get("path")


def test_smoothness_includes_timeout_reason_path():
    from core.smoothness import compute

    s = compute()
    assert "score" in s
    assert "grade" in s
    assert isinstance(s["reasons"], list)
    # reasons should mention queue or honest or latency/timeout
    joined = " ".join(str(x) for x in s["reasons"]).lower()
    assert any(
        k in joined
        for k in ("queue", "honest", "latency", "timeout", "critique", "frozen")
    )


def test_whats_next_no_dual_dashboard_blocker():
    from scripts.write_whats_next import main

    assert main() == 0
    import json
    from pathlib import Path

    data = json.loads(
        (Path(__file__).resolve().parents[1] / "artifacts" / "whats_next.json").read_text(
            encoding="utf-8"
        )
    )
    blocked = " ".join(data.get("blocked") or [])
    assert "dual_dashboard" not in blocked
    resolved = " ".join(data.get("resolved") or [])
    assert "host-first" in resolved.lower() or "dual_dashboard" in resolved.lower()


def test_ast_edit_kpi_runs():
    from core.ast_edit_kpi import compute

    a = compute()
    assert "multifile_n" in a
    assert "primary" in a
