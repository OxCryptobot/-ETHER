"""p3_60: multi-agent coordination is sequential + FIFO. Spawn stays false."""
from core.loop.coord import MAX_LIVE_AGENTS, SPAWNED, assert_single_consumer
from core.phase4_swarm_plan import plan


def test_identity_one_live_agent():
    assert MAX_LIVE_AGENTS == 1
    assert SPAWNED is False


def test_swarm_plan_does_not_spawn():
    payload = plan("implement and test feature", max_agents=4)
    assert payload["spawned"] is False
    assert payload["gpu"] is False
    assert payload["n_agents"] >= 1
    assert all(a.get("live") is False for a in payload["agents"])
    assert_single_consumer(payload)


def test_assert_rejects_spawn():
    try:
        assert_single_consumer({"spawned": True, "gpu": False, "agents": []})
    except AssertionError:
        return
    raise AssertionError("expected spawn reject")
