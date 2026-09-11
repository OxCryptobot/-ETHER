"""Living contract: planner + outbox + living_ok lane. 4B optional."""
from core.loop.live_attach import publish
from core.loop.plan_drive import tools_for_plan
from core.loop.stream_obs import stream_observation


def test_living_contract_fast() -> None:
    tools = tools_for_plan("living")
    assert tools[0] == "list_files"
    assert "run_tests" in tools
    streamed = stream_observation("run_tests", {"ok": True}, job_id="living_contract")
    assert streamed["lane"] == "outbox"
    att = publish()
    assert att["fast_lane"] == "matrix-worker"
    assert att["live_lane"] in {"ollama_4b", "grok_bus", "none"}
    if att["live_lane"] != "none":
        assert att.get("living_ok") is True
