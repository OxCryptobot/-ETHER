"""(1+lambda)-ES prototype: offline only, behind a flag, never promotes."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from core.agent import evolve_es, outcome



@pytest.fixture(autouse=True)
def _legacy_ladder(monkeypatch):
    """These tests pin the legacy ladder (retired by default in batch 2)."""
    monkeypatch.setenv("ETHER_SOTA_LEGACY", "1")
    monkeypatch.setenv("ETHER_GOAL_SOURCE", "0")

def test_snips_matches_hand_math() -> None:
    data = [("b", "x", 0.5, 1.0), ("b", "y", 0.5, 0.0)]
    value, ess = evolve_es.snips({"b": {"x": 1.0, "y": 0.0}}, data)
    assert value == pytest.approx(1.0)
    assert ess == pytest.approx(1.0)
    value, ess = evolve_es.snips({"b": {"x": 0.5, "y": 0.5}}, data)
    assert value == pytest.approx(0.5)
    assert ess == pytest.approx(2.0)


def test_split_is_deterministic_and_disjoint() -> None:
    data = list(range(20))
    a1, b1 = evolve_es.split(data, seed=3)
    a2, b2 = evolve_es.split(data, seed=3)
    assert (a1, b1) == (a2, b2)
    assert sorted(a1 + b1) == data and len(a1) == 14


def test_es_moves_toward_the_arm_that_passes() -> None:
    rng = random.Random(0)
    data = []
    for _ in range(400):
        arm = rng.choice(["good", "bad"])
        ok = rng.random() < (0.8 if arm == "good" else 0.1)
        data.append(("b", arm, 0.5, 1.0 if ok else 0.0))
    seed = {"b": {"good": 0.0, "bad": 0.0}}
    genome, fit = evolve_es.evolve(seed, data, rng=random.Random(1))
    assert fit > evolve_es.fitness(seed, data, anchor=seed)
    assert evolve_es.phenotype(genome)["b"]["good"] > 0.5


def _log(root: Path, n: int, rng: random.Random) -> None:
    for _ in range(n):
        arm = rng.choice(["default", "minimal"])
        ok = rng.random() < (0.9 if arm == "minimal" else 0.2)
        kind = "pass" if ok else "fail"
        outcome._append(root, {"bucket": "gen|simple", "arm": arm, "propensity": 0.5,
                               "kind": kind, "tests_ok": ok, "reward": outcome.reward_for(kind)})


def test_propose_writes_a_candidate_and_never_promotes(tmp_path: Path) -> None:
    _log(tmp_path, 200, random.Random(2))
    row = evolve_es.propose(tmp_path, rng=random.Random(3))
    assert row["n"] == 200 and row["n_holdout"] == 60
    saved = json.loads((tmp_path / "memory" / "learning" / "es_candidate.json").read_text(encoding="utf-8"))
    assert saved["accepted"] == row["accepted"]
    assert not outcome.promoted_path(tmp_path).exists()


def test_flag_off_means_the_es_is_never_sampled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.spine.state_io import write_json

    write_json(tmp_path / "memory" / "learning" / "es_candidate.json",
               {"accepted": True, "policy": {"gen|simple": {"minimal": 1.0}}})
    monkeypatch.delenv("ETHER_NEURO_ES", raising=False)
    pick = outcome.choose(tmp_path, explore=True)
    assert pick.reason != "es"
    monkeypatch.setenv("ETHER_NEURO_ES", "1")
    pick = outcome.choose(tmp_path, explore=True)
    assert pick.reason == "es" and pick.arm == "minimal" and pick.propensity == pytest.approx(1.0)
    # exploration off: ES is ignored even with the flag on
    assert outcome.choose(tmp_path, explore=False).reason == "incumbent"


def test_unaccepted_candidate_is_not_sampled(tmp_path: Path) -> None:
    from core.spine.state_io import write_json

    write_json(tmp_path / "memory" / "learning" / "es_candidate.json",
               {"accepted": False, "policy": {"gen|simple": {"minimal": 1.0}}})
    assert evolve_es.sample(tmp_path, "gen|simple") is None
