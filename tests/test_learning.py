from core.learning import BanditPolicy, compute_reward, strategy_prompt_addon


def test_reward_success():
    r = compute_reward(exit_code=0, confidence=1.0, audit_approved=True, retries=0)
    # calibrated to roughly [-1, 1]; perfect path ~1.0
    assert r >= 0.8
    assert r <= 1.0


def test_reward_failure():
    r = compute_reward(exit_code=1, confidence=0.1, audit_approved=False, retries=2)
    assert r < 0


def test_bandit_updates(tmp_path, monkeypatch):
    path = tmp_path / "bandit.json"
    monkeypatch.setenv("ETHER_LEARNING", "1")
    b = BanditPolicy(epsilon=0.0)
    # point storage at tmp for isolation
    import core.learning as L

    monkeypatch.setattr(L, "BANDIT_PATH", path)
    b = BanditPolicy(epsilon=0.0)
    b.update("minimal", 0.9)
    b.update("default", 0.1)
    assert b.arms["minimal"].mean_reward > b.arms["default"].mean_reward
    picks = {b.select() for _ in range(15)}
    assert "minimal" in picks


def test_strategy_addon():
    assert "shortest" in strategy_prompt_addon("minimal").lower()
