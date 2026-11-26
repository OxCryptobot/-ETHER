"""Tests for scripts/swarm_sim.py — live identities, honest-gate accounting, option mechanics.

These are simulation-unit tests (fixed seeds, short horizons). They do not claim 1650
measurements. The checked-in results file is produced by the script, not by this file.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import pytest

from scripts import swarm_sim as S


def test_live_identity_recovers_published_rates():
    ident = S.analytic_live_identity()
    assert ident["p_keep"] == pytest.approx(2 / 238)
    assert ident["p_keep"] == pytest.approx(0.00840336, rel=1e-6)
    assert ident["secs_per_attempt"] == pytest.approx(14.903 * 3600 / 238)
    assert ident["kept_per_gpu_hour"] == pytest.approx(2 / 14.903)
    assert round(ident["kept_per_gpu_hour"], 3) == S.LIVE_KEPT_PER_GPU_HOUR
    assert sum(S.VIA_N.values()) == S.LIVE_REAL_GRADED
    assert sum(S.VIA_KEEP.values()) == S.LIVE_REAL_PASSES


def test_via_mle_matches_live_by_via():
    rates = S.mle_rates()
    assert rates["sbfl"] == 0.0
    assert rates["lint"] == 0.0
    assert rates["test_import"] == pytest.approx(2 / 87)
    assert S.live_p(rates) == pytest.approx(2 / 238)
    # Laplace must not rank lint above the only via that has kept.
    lap = S.laplace_rates()
    assert lap["lint"] <= lap["test_import"] + 1e-12
    assert lap["sbfl"] > 0.0


def test_expected_solo_cost_fits_live_regression_times():
    # 160+30+55 = 245 s, in the live regression band 245–272 s.
    assert S.T_BASE + S.T_MODEL + S.T_AFTER == 245.0
    cost = S.analytic_baseline_cost()
    assert cost == pytest.approx(160 + 30 + 0.8 * 55)
    assert 190.0 < cost < 245.0  # some attempts skip the after-gate


def test_keep_always_pays_the_after_gate():
    """Honest gate: a keep is impossible without paying T_AFTER (pregate cannot PASS)."""
    scen = S.build_scenarios()["homogeneous"]
    opt = next(o for o in S.OPTIONS if o.name == "zero_model")
    keeps = 0
    for s in range(400):
        a = S.run_attempt(opt, scen, random.Random(s), via="test_import")
        if a.kept:
            keeps += 1
            assert a.after_gates == 1
            assert a.false_reject == 0
            assert a.secs >= scen.t_base + scen.t_model + scen.t_after
        if a.false_reject or a.veto or a.no_edit:
            assert a.kept == 0
            assert a.after_gates == 0
    assert keeps >= 1  # test_import MLE is ~0.023; 400 tries is enough


def test_baseline_never_saves_an_after_gate_or_adds_a_model_call():
    scen = S.build_scenarios()["homogeneous"]
    opt = next(o for o in S.OPTIONS if o.name == "baseline")
    a = S.run_attempt(opt, scen, random.Random(0), via="test_import")
    assert a.model_calls == 1
    assert a.after_saved == 0
    # Either no-edit (no after-gate) or one after-gate; never a veto skip.
    assert a.veto == 0
    assert a.after_gates in (0, 1)
    if a.no_edit:
        assert a.after_gates == 0
        assert a.secs == pytest.approx(scen.t_base + scen.t_model)
    else:
        assert a.after_gates == 1
        assert a.secs == pytest.approx(scen.t_base + scen.t_model + scen.t_after)


def test_bon_uses_n_serial_proposer_calls_and_at_most_one_after_gate():
    scen = S.build_scenarios()["homogeneous"]
    for n, name in ((2, "bon2"), (4, "bon4")):
        opt = next(o for o in S.OPTIONS if o.name == name)
        a = S.run_attempt(opt, scen, random.Random(1), via="test_import")
        assert a.model_calls == n
        assert a.after_gates in (0, 1)
        assert a.after_gates + a.after_saved + a.no_edit == 1
        assert a.secs >= scen.t_base + n * scen.t_model


def test_debate_and_moa_cost_more_model_calls_than_solo():
    scen = S.build_scenarios()["homogeneous"]
    rng = random.Random(2)
    solo = S.run_attempt(next(o for o in S.OPTIONS if o.name == "baseline"), scen, rng, via="test_import")
    debate = S.run_attempt(next(o for o in S.OPTIONS if o.name == "debate"), scen, random.Random(2), via="test_import")
    moa = S.run_attempt(next(o for o in S.OPTIONS if o.name == "moa"), scen, random.Random(2), via="test_import")
    assert debate.model_calls == 3  # proposer + critic + judge
    assert moa.model_calls == 5     # 4 proposers + aggregator
    assert debate.model_calls > solo.model_calls
    assert moa.model_calls > debate.model_calls


def test_4b_critic_can_only_veto_never_pass_without_a_gate():
    scen = S.build_scenarios()["homogeneous"]
    opt = next(o for o in S.OPTIONS if o.name == "critic_4b")
    assert opt.llm_veto and opt.extra_roles == 1
    for s in range(200):
        a = S.run_attempt(opt, scen, random.Random(1000 + s), via="test_import")
        assert a.model_calls == 2
        if a.kept:
            assert a.after_gates == 1
        if a.veto:
            assert a.kept == 0 and a.after_gates == 0


def test_pregate_false_reject_never_counts_as_a_keep():
    scen = S.build_scenarios()["homogeneous"]
    opt = next(o for o in S.OPTIONS if o.name == "zero_model")
    # Force a would-keep, then a guaranteed kill, by patching rates through p_each
    # and a high kill — we just assert the accounting on observed false rejects.
    seen = 0
    for s in range(2000):
        a = S.run_attempt(opt, scen, random.Random(s), via="test_import")
        if a.false_reject:
            seen += 1
            assert a.kept == 0 and a.after_gates == 0 and a.after_saved == 1
    # 2000 * ~0.023 * 0.01 is ~0.5 expected; don't require it, just the invariant.


def test_unique_samples_bounds_and_duplicates():
    rng = random.Random(0)
    assert S._unique_samples(1, 0.99, rng) == 1
    assert S._unique_samples(5, 0.0, random.Random(0)) == 5
    u = [S._unique_samples(8, 1.0, random.Random(s)) for s in range(20)]
    assert all(x == 1 for x in u)


def test_loc_off_does_not_lift_sbfl_rate():
    off = S.build_scenarios()["loc_off"]
    strong = S.build_scenarios()["loc_strong"]
    assert off.p_of("sbfl", loc=True) == 0.0
    assert strong.p_of("sbfl", loc=True) == pytest.approx(0.40 * (2 / 87))
    assert strong.p_of("sbfl", loc=False) == 0.0


def test_iid_baseline_at_live_horizon_is_near_live_p(monkeypatch):
    """Monte Carlo around the MLE, not the live 225 s blend (timeouts excluded)."""
    scen = S.build_scenarios()["homogeneous"]
    opt = next(o for o in S.OPTIONS if o.name == "baseline")
    rows = [S.run_iid(opt, scen, 238, random.Random(s)) for s in range(40)]
    summary = S.summarise(rows, "iid")
    assert summary["kept_per_attempt"] == pytest.approx(2 / 238, abs=0.01)
    assert summary["model_calls_per_attempt"] == pytest.approx(1.0)
    assert summary["filler_rate"] == 0.0
    assert summary["planted_share"] == 0.0


def test_goal_flow_and_planted_do_not_dry_out_a_pool():
    scen = S.build_scenarios()["homogeneous"]
    wall = 6 * 3600  # 6 h
    dry = S.run_pool(next(o for o in S.OPTIONS if o.name == "baseline"), scen, wall, random.Random(0), n_goals=8)
    wet = S.run_pool(next(o for o in S.OPTIONS if o.name == "goal_flow"), scen, wall, random.Random(0), n_goals=8)
    combo = S.run_pool(next(o for o in S.OPTIONS if o.name == "zero_plus_flow"), scen, wall, random.Random(0), n_goals=8)
    assert dry.dry is True and dry.idle_s > 0
    assert wet.dry is False and wet.idle_s == 0
    assert combo.dry is False and combo.idle_s == 0
    assert wet.planted_attempts > 0 or combo.planted_attempts > 0


def test_pool_spends_tries_and_retires_a_keep():
    scen = S.build_scenarios()["homogeneous"]
    opt = next(o for o in S.OPTIONS if o.name == "baseline")
    rng = random.Random(1)
    pool = S.make_pool(9, scen, loc=False, rng=rng)
    assert len(pool) == 9
    assert all(g.tries == S.MAX_TRIES for g in pool)
    # A keep on a goal must zero its remaining tries (resolved).
    # Drive this through run_pool with a tiny wall and inspect via attempts <= 9*3.
    row = S.run_pool(opt, scen, wall_s=10_000, rng=random.Random(2), n_goals=5)
    assert row.attempts <= 5 * S.MAX_TRIES
    assert row.dry is True


def test_expensive_model_makes_bon_cost_more_per_attempt_than_baseline():
    scen = S.build_scenarios()["expensive_model"]
    base = next(o for o in S.OPTIONS if o.name == "baseline")
    bon = next(o for o in S.OPTIONS if o.name == "bon2")
    b = S.summarise([S.run_iid(base, scen, 80, random.Random(s)) for s in range(15)], "iid")
    n = S.summarise([S.run_iid(bon, scen, 80, random.Random(s)) for s in range(15)], "iid")
    assert n["model_calls_per_attempt"] == pytest.approx(2.0)
    # Per-attempt seconds must rise (one extra 90 s call, even if an after-gate is skipped).
    assert n["secs"] / n["attempts"] > b["secs"] / b["attempts"]


def test_suite_smoke_is_reproducible_and_ranked():
    out1 = S.run_suite(seeds=3, horizons=[40], wall_s=1800, seed0=11)
    out2 = S.run_suite(seeds=3, horizons=[40], wall_s=1800, seed0=11)
    assert out1["scenarios"]["homogeneous"]["iid"]["40"]["baseline"] == out2["scenarios"]["homogeneous"]["iid"]["40"]["baseline"]
    names = {r["option"] for r in out1["ranking"]["rows"]}
    assert names == {o.name for o in S.OPTIONS}
    # No option may report a keep that skipped the honest-gate identity in the schema:
    # after_gates + after_saved + no_edit accounts for every attempt in expectation
    # (checked per-attempt in other tests). Ranking must include the live identity.
    assert out1["live"]["kept_per_attempt"] == pytest.approx(0.0084, abs=5e-5)
    assert "homogeneous" in out1["scenarios"] and "sparse" in out1["scenarios"]


def test_checked_in_results_exist_and_are_labelled_simulation():
    path = Path(__file__).resolve().parents[1] / "docs/results/swarm/swarm_sim.json"
    if not path.is_file():
        pytest.skip("swarm_sim.json not generated yet")
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "SIMULATION" in data["label"]
    assert data["live"]["real_graded"] == 238
    assert data["live"]["real_passes"] == 2
    assert set(data["ranking"]["rows"][0]) >= {"option", "kept_per_attempt", "kept_per_gpu_hour", "verdict"}
