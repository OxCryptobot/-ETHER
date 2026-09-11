"""Living contract: planner tools + outbox stream + attach lanes. Not 4B LIVE."""
from core.loop.live_attach import detect
from core.loop.plan_drive import tools_for_plan
from core.loop.stream_obs import stream_observation


def test_living_contract_fast() -> None:
    tools = tools_for_plan("living")
    assert tools[0] == "list_files"
    assert "run_tests" in tools
    streamed = stream_observation("run_tests", {"ok": True}, job_id="living_contract")
    assert streamed["lane"] == "outbox"
    att = detect()
    assert att["fast_lane"] == "matrix-worker"
    assert att["live_lane"] in {"ollama_4b", "grok_bus"}
