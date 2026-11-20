"""Batch 4: bandit selectors, honest 0/1 reward, published metrics, hub-aware SBFL."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from core.agent import bandit as B
from core.agent import outcome


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("ETHER_BANDIT", "ETHER_BANDIT_GAMMA", "ETHER_BANDIT_COST", "ETHER_BANDIT_ARMS",
              "ETHER_BANDIT_FACTORED", "ETHER_SOTA_EXPLORE", "ETHER_PROMOTE_RULE", "ETHER_SBFL_RANK"):
        monkeypatch.delenv(k, raising=False)


# ---------------------------------------------------------------- pure selectors

def test_thompson_finds_the_better_arm_with_a_fixed_seed() -> None:
    rng = random.Random(0)
    stats: dict = {}
    truth = {"default": 0.10, "minimal": 0.08, "repair_heavy": 0.12, "no_context": 0.03, "repo_map_on": 0.30}
    pulls = {a: 0 for a in truth}
    for _ in range(400):
        arm, _ = B.select("thompson", stats, list(truth), rng)
        pulls[arm] += 1
        B.update(stats, arm, int(rng.random() < truth[arm]), secs=40.0)
    assert max(pulls, key=pulls.get) == "repo_map_on"
    assert pulls["repo_map_on"] > 200


def test_ucb_covers_untried_arms_first() -> None:
    rng = random.Random(1)
    stats: dict = {}
    seen = []
    for _ in range(5):
        arm, reason = B.select("ucb", stats, list(B.REAL_ARMS), rng)
        assert reason == "cover"
        seen.append(arm)
        B.update(stats, arm, 0)
    assert sorted(seen) == sorted(B.REAL_ARMS)
    assert B.select("ucb", stats, list(B.REAL_ARMS), rng)[1] == "ucb"


def test_propensities_sum_to_one_and_discount_forgets() -> None:
    stats: dict = {}
    for _ in range(6):
        B.update(stats, "minimal", 1)
    B.update(stats, "default", 0)
    arms = list(B.REAL_ARMS)
    total = sum(B.propensity("thompson", stats, arms, a, seed=3, draws=500) for a in arms)
    assert abs(total - 1.0) < 0.02
    p_min = B.propensity("thompson", stats, arms, "minimal", seed=3)
    assert p_min > 10 * B.propensity("thompson", stats, arms, "default", seed=3)
    assert B.prior(stats) == pytest.approx((2 * 7 / 9, 2 * 2 / 9))  # pooled: 6 passes, 1 fail
    before = stats["minimal"]["s"]
    B.update(stats, "default", 0, g=0.9)
    assert stats["minimal"]["s"] == pytest.approx(before * 0.9)
    assert stats["minimal"]["n"] == 6  # pull counts are never discounted


def test_cost_aware_prefers_cheap_arms_at_equal_pass_rate() -> None:
    stats: dict = {}
    for _ in range(40):
        B.update(stats, "default", 1, secs=40.0)
        B.update(stats, "default", 0, secs=40.0)
        B.update(stats, "repair_heavy", 1, secs=90.0)
        B.update(stats, "repair_heavy", 0, secs=90.0)
    p_cheap = B.propensity("thompson", stats, ["default", "repair_heavy"], "default", seed=1, cost=True)
    assert p_cheap > 0.95


def test_linucb_learns_a_feature_dependent_arm() -> None:
    m = {a: B.lin_new(len(B.FEATURES)) for a in ("default", "repo_map_on")}
    sbfl = B.features({"via": "sbfl", "kind": "fix_test"})
    frame = B.features({"via": "frame", "kind": "fix_test"})
    for _ in range(60):
        B.lin_update(m["repo_map_on"], sbfl, 1.0)
        B.lin_update(m["default"], sbfl, 0.0)
        B.lin_update(m["default"], frame, 1.0)
        B.lin_update(m["repo_map_on"], frame, 0.0)
    assert B.lin_score(m["repo_map_on"], sbfl, 0.1) > B.lin_score(m["default"], sbfl, 0.1)
    assert B.lin_score(m["default"], frame, 0.1) > B.lin_score(m["repo_map_on"], frame, 0.1)


def test_factored_arms_map_to_real_behaviour() -> None:
    fb = B.factored_behaviour("f:minimal.none.2")
    assert fb.use_workspace_context is False and "Minimal" in fb.prompt_addon
    assert B.factored_behaviour("f:plain.map.1").force_repo_map is True
    assert B.tries_for("f:plain.file.2") == 2 and B.tries_for("f:plain.file.1") == 1
    assert B.tries_for("repair_heavy") == 2 and B.tries_for("default") == 1
    stats: dict = {}
    arm = B.factored_select(stats, random.Random(0))
    assert arm.startswith("f:") and len(arm[2:].split(".")) == 3
    B.factored_update(stats, arm, 1)
    assert all(stats[lv]["s"] == 1.0 for lv in B.factored_levels(arm))


# ---------------------------------------------------------------- live wiring

def _goal(**kw):
    return {"id": "fix_x", "kind": "fix_test", "file": "pkg/x.py", "symbol": "f", "nodeid": "tests/test_x.py::t",
            "via": "sbfl", "error_kind": "AssertionError", "tractability": 0.4, **kw}


def test_default_selector_for_real_goals_is_thompson_over_real_arms(tmp_path: Path) -> None:
    assert B.algo("fix_test") == "thompson" and B.algo("lint") == "thompson"
    assert B.algo("refactor") == "egreedy" and B.algo("") == "egreedy"
    pick = outcome.choose(tmp_path, goal=_goal())
    assert pick.arm in B.REAL_ARMS and 0 < pick.propensity <= 1 and pick.reason == "sample"
    assert pick.trace["bandit"]["algo"] == "thompson"


def test_egreedy_flag_is_the_batch2_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETHER_BANDIT", "egreedy")
    pick = outcome.choose(tmp_path, goal=_goal())
    assert pick.reason in ("cover", "explore", "exploit") and "bandit" not in pick.trace


def test_explore_off_still_uses_the_promoted_arm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETHER_SOTA_EXPLORE", "0")
    pick = outcome.choose(tmp_path, goal=_goal())
    assert pick.arm == "default" and pick.reason == "incumbent" and pick.propensity == 1.0


def _record(root: Path, result: dict, arm: str = "minimal"):
    pick = outcome.Pick(arm=arm, propensity=0.2, reason="sample", context={"tier": 2, "fail_kind": "tests_failed"},
                        bucket="repair_logic|complex", kind="fix_test")
    pick.trace["secs"] = 42.0
    return outcome.record(root, pick, {"goal": "fix_x", "kind": "fix_test", **result})


def test_reward_is_strictly_the_honest_gate(tmp_path: Path) -> None:
    row = _record(tmp_path, {"ok": True, "honest": True, "tests_ok": True, "regressions": 0})
    assert row["kind"] == "pass" and row["reward01"] == 1
    st = B.load(tmp_path, "fix_test")["buckets"]["repair_logic|complex"]["minimal"]
    assert st["s"] == 1.0 and st["n"] == 1 and st["secs"] == 42.0
    # a self-claimed success without the gate's tests_ok is a fail
    row = _record(tmp_path, {"ok": True, "honest": False, "note": "generated"})
    assert row["kind"] == "fail" and row["reward01"] == 0
    # a pass that broke another test is never a 1
    assert outcome.reward01("pass", {"tests_ok": True, "regressions": 2}) == 0
    # reverted edit
    row = _record(tmp_path, {"ok": False, "honest": False, "note": "regression", "regressions": 1})
    assert row["reward01"] == 0
    st = B.load(tmp_path, "fix_test")["buckets"]["repair_logic|complex"]["minimal"]
    assert st["s"] == 1.0 and st["f"] == 2.0


@pytest.mark.parametrize("result", [
    {"ok": False, "infra": True, "note": "infra: ConnectionError"},
    {"ok": True, "note": "already present"},
    {"ok": False, "note": "rejected: spoiler"},
])
def test_non_model_outcomes_do_not_move_any_bandit(tmp_path: Path, result: dict) -> None:
    row = _record(tmp_path, result)
    assert row["reward"] is None and "reward01" not in row
    assert not B.state_path(tmp_path, "fix_test").exists()
    assert not outcome.bandit_path(tmp_path, "fix_test").exists()


def test_rule_based_refactor_does_not_train_the_model_arms(tmp_path: Path) -> None:
    pick = outcome.Pick(arm="minimal", propensity=1.0, reason="incumbent", context={"tier": 3}, bucket="gen|complex",
                        kind="refactor")
    row = outcome.record(tmp_path, pick, {"goal": "refactor_x", "kind": "refactor", "ok": True, "tests_ok": True,
                                          "regressions": 0, "policy": "tool"})
    assert row["kind"] == "tool" and row["reward"] is None and row["policy"] == "tool"
    assert not outcome.bandit_path(tmp_path, "refactor").exists()
    assert outcome.metrics(tmp_path)["tool_edits"] == 1


def test_state_is_capped_to_allowed_arms_and_buckets(tmp_path: Path) -> None:
    for i in range(B.MAX_BUCKETS + 10):
        B.record(tmp_path, "fix_test", f"b{i}", "default", 1)
    data = B.load(tmp_path, "fix_test")
    data["buckets"]["b0"]["multifile"] = {"s": 9, "f": 0, "n": 9}
    B.save(tmp_path, "fix_test", data)
    data = B.load(tmp_path, "fix_test")
    assert len(data["buckets"]) <= B.MAX_BUCKETS
    assert all("multifile" not in cells for cells in data["buckets"].values())
    assert B.state_path(tmp_path, "fix_test").stat().st_size < 64 * 1024


def test_published_summary_has_metrics_and_bandit(tmp_path: Path) -> None:
    for i in range(30):
        _record(tmp_path, {"ok": i % 3 == 0, "tests_ok": i % 3 == 0, "regressions": 0,
                           "note": "" if i % 3 == 0 else ("regression" if i % 2 else "no function")},
                arm=B.REAL_ARMS[i % 5])
    out = outcome.publish_summary(tmp_path)
    doc = json.loads((tmp_path / outcome.SUMMARY_PATH).read_text(encoding="utf-8"))
    assert out["ok"] and doc["schema"] == 2
    m = doc["metrics"]
    assert m["attempts"] == 30 and m["kept"] == 10 and m["kept_per_attempt"] == pytest.approx(0.3333, abs=1e-3)
    assert m["filler_rate"] == 0.0 and m["revert_rate"] is not None and m["gpu_hours"] > 0
    assert m["kept_per_gpu_hour"] > 0 and m["arm_entropy_bits"]["fix_test"] > 2.0
    assert doc["bandit"]["algo"]["fix_test"] == "thompson"
    cell = doc["bandit"]["fix_test"]["repair_logic|complex"]
    assert sum(c["n"] for c in cell["arms"].values()) == 30 and "p_best" in cell


def test_filler_kept_shows_up_in_the_filler_rate(tmp_path: Path) -> None:
    rows = [{"kind": "pass", "goal": "describe_x", "goal_kind": "legacy", "tests_ok": True},
            {"kind": "pass", "goal": "fix_real", "goal_kind": "fix_test", "tests_ok": True}]
    assert outcome.metrics(tmp_path, rows)["filler_rate"] == 0.5


def test_posterior_promotion_needs_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETHER_PROMOTE_RULE", "posterior")
    for _ in range(3):  # 3 passes from 3 pulls vs an untested incumbent: not enough
        _record(tmp_path, {"ok": True, "tests_ok": True, "regressions": 0}, arm="repo_map_on")
    assert (outcome.promoted(tmp_path) or {}) == {}
    for _ in range(12):
        _record(tmp_path, {"ok": False, "note": "tests failed"}, arm="default")
    _record(tmp_path, {"ok": True, "tests_ok": True, "regressions": 0}, arm="repo_map_on")
    prom = outcome.promoted(tmp_path)
    assert prom["fix_test:repair_logic|complex"]["arm"] == "repo_map_on"
    assert outcome.metrics(tmp_path)["promotions"] == 1


# ---------------------------------------------------------------- SBFL hub demotion

def test_hub_rank_demotes_a_dispatcher_every_test_enters() -> None:
    from core.agent.fault_loc import ochiai, rank

    hub = ["core/registry.py", "GemRegistry.execute"]
    culprit = ["core/pipeline.py", "Pipeline._run_audit"]
    tests = {f"t::p{i}": {"outcome": "passed", "calls": [hub]} for i in range(10)}
    for i in range(4):
        tests[f"t::f{i}"] = {"outcome": "failed", "calls": [hub] + ([culprit] if i == 0 else [])}
    spectra = {"tests": tests}
    assert ochiai(spectra, "t::f0")[0][3] == "GemRegistry.execute"
    assert rank(spectra, "t::f0")[0][3] == "Pipeline._run_audit"
    # the failure's own words break ties toward the named stage
    other = ["core/pipeline.py", "Pipeline._run_critique"]
    tests["t::f0"]["calls"].append(other)
    hint = "AssertionError: audit stage vanished on gem error"
    assert rank(spectra, "t::f0", hint)[0][3] == "Pipeline._run_audit"


def test_sbfl_rank_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.agent import goal_source as gs

    assert gs.sbfl_rank() == "hub"
    monkeypatch.setenv("ETHER_SBFL_RANK", "ochiai")
    assert gs.sbfl_rank() == "ochiai"


# ---------------------------------------------------------------- simulator

def test_simulator_is_deterministic_and_thompson_beats_uniform() -> None:
    from scripts import bandit_sim as S

    a = S.run_one(("mid", "thompson-5", 300, 3))
    assert a == S.run_one(("mid", "thompson-5", 300, 3))
    ts = [S.run_one(("mid", "thompson-5", 300, s))["regret"] for s in range(12)]
    un = [S.run_one(("mid", "uniform-5", 300, s))["regret"] for s in range(12)]
    assert sum(ts) < sum(un)


def test_snips_recovers_a_policy_value_from_logged_propensities() -> None:
    from scripts import bandit_sim as S

    rng = random.Random(5)
    truth = {"default": 0.1, "repo_map_on": 0.4}
    logged = []
    for _ in range(4000):
        arm = "default" if rng.random() < 0.8 else "repo_map_on"
        logged.append({"arm": arm, "propensity": 0.8 if arm == "default" else 0.2,
                       "reward01": int(rng.random() < truth[arm])})
    assert S.snips(logged, {"repo_map_on": 1.0}) == pytest.approx(0.4, abs=0.04)
    assert S.snips(logged, {"default": 0.5, "repo_map_on": 0.5}) == pytest.approx(0.25, abs=0.03)


def test_logging_sinks_are_demoted() -> None:
    from core.agent.fault_loc import rank

    sink = ["core/pipeline.py", "Pipeline._log"]
    cause = ["core/pipeline.py", "Pipeline._stage"]
    tests = {f"t::p{i}": {"outcome": "passed", "calls": [cause]} for i in range(2)}
    tests["t::f0"] = {"outcome": "failed", "calls": [cause, sink]}
    tests["t::p9"] = {"outcome": "passed", "calls": []}
    top = rank({"tests": tests}, "t::f0")[0]
    assert top[3] == "Pipeline._stage"


def test_reply_cap_follows_the_target_and_too_large_targets_are_dropped(tmp_path: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    from core.agent import goal_source as gs

    small = "def small(x):\n    return x + 1\n"
    big = "def big(x):\n" + "".join(f"    x = x + {i}  # step {i} of a long routine\n" for i in range(120)) + "    return x\n"
    mid = "def mid(x):\n" + "".join(f"    x = x * {i} + {i}\n" for i in range(40)) + "    return x\n"
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text(small + "\n\n" + mid + "\n\n" + big, encoding="utf-8")
    g = {"kind": "fix_test", "file": "pkg/m.py"}
    assert gs.reply_tokens(tmp_path, {**g, "symbol": "small"}) == gs.REPLY_MIN
    n_mid = gs.reply_tokens(tmp_path, {**g, "symbol": "mid"})
    assert gs.REPLY_MIN < n_mid <= gs.reply_max()
    assert gs.fits_reply(tmp_path, {**g, "symbol": "mid"})
    assert not gs.fits_reply(tmp_path, {**g, "symbol": "big"})
    assert gs.reply_tokens(tmp_path, {**g, "symbol": "big"}) == gs.reply_max()
    monkeypatch.setenv("ETHER_REPLY_MAX", "4000")
    assert gs.fits_reply(tmp_path, {**g, "symbol": "big"})
    assert "too_large" in gs.DROP_REASONS


def test_react_passes_the_reply_cap_to_the_model(tmp_path: Path) -> None:
    from core.agent.react import react

    seen = []

    def ask(prompt: str, n: int = 240) -> str:
        seen.append(n)
        return "def f():\n    return 1\n"

    react(ask, tmp_path, "fix f", turns=2, n=512)
    assert seen and set(seen) == {512}
