"""Honest-gate reward -> existing bandit, trajectories in memory, gated promote."""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from core.agent import outcome



@pytest.fixture(autouse=True)
def _legacy_ladder(monkeypatch):
    """These tests pin the legacy ladder (retired by default in batch 2)."""
    monkeypatch.setenv("ETHER_SOTA_LEGACY", "1")
    monkeypatch.setenv("ETHER_GOAL_SOURCE", "0")

def _root(tmp_path: Path) -> Path:
    kernel = tmp_path / "core" / "kernel"
    kernel.mkdir(parents=True)
    (tmp_path / "core" / "__init__.py").write_text("", encoding="utf-8")
    (kernel / "__init__.py").write_text("", encoding="utf-8")
    (kernel / "context_budget.py").write_text(
        "def context_char_budget(model_ctx=None):\n    return 7200\n", encoding="utf-8"
    )
    return tmp_path


def _bandit(root: Path) -> dict:
    return json.loads(outcome.bandit_path(root).read_text(encoding="utf-8"))


def test_a_pass_rewards_the_existing_bandit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.agent.sota import run
    from core.learning import STRATEGIES

    monkeypatch.delenv("ETHER_SOTA_EXPLORE", raising=False)
    root = _root(tmp_path)
    prompts = []

    def ask(prompt: str, n: int = 240) -> str:
        prompts.append(prompt)
        return "def packed_count(text: str) -> int:\n    return text.count('### ')\n"

    row = run(root, ask)
    assert "packed_count" in row["batch"]
    data = _bandit(root)
    assert set(STRATEGIES) <= set(data["arms"])
    assert data["arms"]["default"]["pulls"] >= 1
    traj = outcome.trajectories(root)
    assert traj[0]["kind"] == "pass" and traj[0]["tests_ok"] is True
    assert traj[0]["reward"] > 0
    assert sum(1 for r in traj if r["kind"] in ("pass", "fail")) == data["arms"]["default"]["pulls"]
    assert traj[0]["spoiler"] is True  # the ladder prompt contains the answer
    # incumbent arm adds nothing to the prompt
    assert not any("Minimal code only" in p for p in prompts)


def test_a_fail_is_negative_and_infra_is_not_a_lesson(tmp_path: Path) -> None:
    from core.agent.sota import run

    root = _root(tmp_path)
    run(root, lambda prompt, n=240: "I am not sure")
    data = _bandit(root)
    assert data["arms"]["default"]["total_reward"] < 0
    pulls = data["arms"]["default"]["pulls"]

    root2 = _root(tmp_path / "b")

    def down(prompt: str, n: int = 240) -> str:
        raise urllib.error.URLError("refused")

    run(root2, down)
    assert not outcome.bandit_path(root2).exists()
    assert outcome.trajectories(root2)[0]["kind"] == "infra"
    assert pulls == 1


def _seed(root: Path, arm: str, kinds: list) -> None:
    pol = outcome.policy(root)
    ctx = {"tier": 0, "fail_kind": "", "multifile": False}
    for kind in kinds:
        pick = outcome.Pick(arm=arm, propensity=0.5, reason="explore", context=ctx, bucket="gen|simple")
        outcome._append(root, {"bucket": "gen|simple", "arm": arm, "kind": kind,
                               "tests_ok": kind == "pass", "reward": outcome.reward_for(kind)})
        pol.update(pick.arm, outcome.reward_for(kind), context=ctx)


def test_promote_needs_three_honest_passes(tmp_path: Path) -> None:
    _seed(tmp_path, "default", ["fail", "pass", "fail"])
    _seed(tmp_path, "minimal", ["pass", "pass"])
    assert outcome.maybe_promote(tmp_path, "gen|simple")["action"] == "hold"
    _seed(tmp_path, "minimal", ["pass"])
    row = outcome.maybe_promote(tmp_path, "gen|simple")
    assert row["action"] == "promote" and row["arm"] == "minimal"
    pick = outcome.choose(tmp_path, explore=False)
    assert pick.arm == "minimal" and pick.addon


def test_no_promote_when_last_attempt_failed(tmp_path: Path) -> None:
    _seed(tmp_path, "default", ["fail", "fail"])
    _seed(tmp_path, "with_asserts", ["pass", "pass", "pass", "fail"])
    assert outcome.maybe_promote(tmp_path, "gen|simple")["action"] == "hold"


def test_a_promoted_arm_is_demoted_after_three_fails(tmp_path: Path) -> None:
    _seed(tmp_path, "default", ["fail"])
    _seed(tmp_path, "minimal", ["pass", "pass", "pass"])
    assert outcome.maybe_promote(tmp_path, "gen|simple")["action"] == "promote"
    _seed(tmp_path, "minimal", ["fail", "fail", "fail"])
    assert outcome.maybe_promote(tmp_path, "gen|simple")["action"] == "demote"
    assert outcome.choose(tmp_path, explore=False).arm == "default"


def test_explore_logs_a_valid_propensity(tmp_path: Path) -> None:
    from core.learning import STRATEGIES

    _seed(tmp_path, "default", ["pass", "fail"])
    pol = outcome.policy(tmp_path)
    for arm in STRATEGIES:
        if arm != "default":
            pol.update(arm, -0.5, context={"tier": 0, "fail_kind": "", "multifile": False})
    total = sum(outcome.propensity_of(pol, "gen|simple", arm, "exploit") for arm in STRATEGIES)
    assert abs(total - 1.0) < 1e-6
    pick = outcome.choose(tmp_path, explore=True)
    assert pick.arm in STRATEGIES and 0 < pick.propensity <= 1


def test_queue_empty_is_not_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.agent import sota

    monkeypatch.setattr(sota, "next_goal", lambda root, **kw: None)
    row = sota.run(tmp_path, lambda prompt, n=240: "")
    assert row["note"] == "queue empty"
    assert outcome.trajectories(tmp_path) == []


def test_trajectories_are_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(outcome, "MAX_TRAJ", 5)
    for i in range(12):
        outcome._append(tmp_path, {"i": i})
    rows = outcome.trajectories(tmp_path)
    assert [r["i"] for r in rows] == [7, 8, 9, 10, 11]
