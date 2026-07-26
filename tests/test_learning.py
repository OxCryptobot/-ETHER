from core.learning import BanditPolicy, compute_reward, strategy_prompt_addon


def test_reward_success():
    r = compute_reward(exit_code=0, confidence=1.0, audit_approved=True, retries=0)
    assert r >= 1.5


def test_reward_failure():
    r = compute_reward(exit_code=1, confidence=0.1, audit_approved=False, retries=2)
    assert r < 0


def test_bandit_updates(tmp_path):
    path = tmp_path / "bandit.json"
    b = BanditPolicy(epsilon=0.0, path=path)
    b.update("minimal", 1.5)
    b.update("default", 0.2)
    assert b.arms["minimal"].mean > b.arms["default"].mean
    # exploit should prefer minimal
    picks = {b.select() for _ in range(10)}
    assert "minimal" in picks


def test_strategy_addon():
    assert "shortest" in strategy_prompt_addon("minimal").lower()
