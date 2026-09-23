from uuid import uuid4

from core.schemas import CitrineRequest, Envelope
from gems.citrine.memory import Citrine


def test_citrine_health_when_qdrant_down() -> None:
    gem = Citrine(qdrant_url="http://127.0.0.1:1", connect=False)
    res = gem.execute(
        Envelope(task_id=uuid4(), target_gem="citrine", payload=CitrineRequest(action="health"))
    )
    assert res.error is None
    assert res.payload is not None
    assert res.payload.action == "health"
