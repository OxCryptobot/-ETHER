from uuid import uuid4
from core.schemas import Envelope, SeleniteRequest, SeleniteResponse
from gems.selenite.planner import Selenite


def test_selenite_basic_plan():
    gem = Selenite()
    req = Envelope(task_id=uuid4(), target_gem="selenite", payload=SeleniteRequest(user_query="implement login"))
    res = gem.execute(req)
    assert res.error is None
    assert isinstance(res.payload, SeleniteResponse)
    assert len(res.payload.plan.steps) >= 2
