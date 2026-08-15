"""Moonshot batch — additive panels must not break defaults."""
from __future__ import annotations

from core.latency_slo import compute as latency_slo
from core.honest_sparkline import compute as sparkline
from core.context_budget import measure as context_measure
from core.scoreboard_rollup import rollup
from core.shadow_tag import compute as shadow
from core.model_router import select_model, status as router_status
from core.gem_energy import publish as gem_energy
from core.ast_edit_kpi import compute as ast_kpi
from core.zero_click_recovery import maybe_recover
from core.microbench import run as microbench
from core.smoothness import compute as smoothness
from core.queue_governor import may_enqueue_steady, training_wheels_on
from core.job_class import job_class, LIVE, FAST


def test_latency_slo_shape():
    out = latency_slo()
    assert "scripted" in out and "live" in out
    assert "alert" in out


def test_sparkline_shape():
    out = sparkline()
    assert "sparkline" in out
    assert out["n"] >= 0


def test_context_budget():
    out = context_measure("hello world " * 100, query="test")
    assert out["out_chars"] <= out["max_chars"] or out["raw_chars"] < out["max_chars"]


def test_rollup_and_shadow():
    r = rollup()
    assert "honest_rate" in r or r.get("n_rows") is not None
    s = shadow()
    assert "n_tags" in s


def test_model_router_lanes():
    fast = select_model({"class": "fast", "note": "pytest"})
    live = select_model({"class": "live", "note": "live ledger"})
    assert fast["lane"] == "fast"
    assert live["lane"] == "live"
    assert router_status()["fast_model"]


def test_gem_ast_smooth():
    assert gem_energy()["gems"]
    assert "multifile_n" in ast_kpi()
    sm = smoothness()
    assert 0 <= sm["score"] <= 100


def test_zero_click_no_fire_on_ok():
    assert maybe_recover({"ok": True}) is None


def test_microbench_runs():
    out = microbench()
    assert "ok" in out
    assert "steps" in out


def test_training_wheels_default_on():
    assert training_wheels_on() is True


def test_fast_before_live_class():
    assert job_class({"class": "live", "note": "live"}) == LIVE
    assert job_class({"class": "fast", "note": "pytest"}) == FAST


def test_pipeline_still_imports():
    from core.pipeline import Pipeline

    assert Pipeline is not None
