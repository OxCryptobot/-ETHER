"""Learning / process reward tests."""

from core.learning import BanditPolicy, compute_reward


def test_reward_success():
    r = compute_reward(
        exit_code=0,
        confidence=1.0,
        audit_approved=True,
        retries=0,
        verification_score=1.0,
        had_self_check=True,
        plan_ok=True,
        first_compile_ok=True,
    )
    assert r >= 0.5


def test_reward_no_tests_weaker():
    strong = compute_reward(
        exit_code=0,
        confidence=0.9,
        audit_approved=True,
        verification_score=1.0,
        had_self_check=True,
        plan_ok=True,
        first_compile_ok=True,
    )
    weak = compute_reward(
        exit_code=0,
        confidence=0.9,
        audit_approved=True,
        verification_score=0.0,
        had_self_check=False,
        plan_ok=True,
        first_compile_ok=True,
    )
    assert strong > weak


def test_reward_failure():
    r = compute_reward(exit_code=1, confidence=0.0, audit_approved=False, plan_ok=True)
    assert r < 0


def test_bandit_updates(tmp_path):
    path = tmp_path / "bandit.json"
    b = BanditPolicy(epsilon=0.0, path=path)
    s = b.select()
    b.update(s, 1.0)
    assert b.arms[s].pulls >= 1
