"""pipeline_score pure helpers — no Pipeline.run."""
from __future__ import annotations


def test_clamp_score():
    from core.pipeline_score import clamp_score

    assert clamp_score(1.5) == 1.0
    assert clamp_score(-0.2) == 0.0
    assert clamp_score(0.42) == 0.42
    assert clamp_score("bad", default=0.25) == 0.25


def test_merge_degraded_dedupes():
    from core.pipeline_score import merge_degraded

    assert merge_degraded(["a", "b"], "b", "c") == ["a", "b", "c"]
    assert merge_degraded(None, "x") == ["x"]


def test_terminal_envelopes():
    from core.pipeline_score import terminal_fail_envelope, terminal_ok_envelope

    fail = terminal_fail_envelope(stage="tool_runtime", marker="tool_runtime_failed_terminal")
    assert fail["ok"] is False
    assert "tool_runtime_failed_terminal" in fail["degraded"]

    ok = terminal_ok_envelope(score=0.9)
    assert ok["ok"] is True
    assert ok["score"] == 0.9


def test_strangler_lists_pipeline_score():
    from core.pipeline_strangler import EXTRACTED, compute

    mods = {e["mod"] for e in EXTRACTED}
    assert "core.pipeline_score" in mods
    s = compute()
    assert s["score_contract_ok"] is True
    assert s["extracted_ok"] == s["extracted_n"]


def test_moonshots_have_strangler_and_ast():
    from dashboard.collector_moonshots import collect_moonshots

    ids = {t["id"] for t in collect_moonshots()["tiles"]}
    assert "strangler" in ids
    assert "ast_edit" in ids
