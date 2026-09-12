"""Local :8787 HTML cockpit is retired."""
from dashboard.app import RETIRED_HTML, index


def test_index_is_tombstone() -> None:
    resp = index()
    assert resp.status_code == 410
    body = resp.body.decode("utf-8") if isinstance(resp.body, (bytes, bytearray)) else str(resp.body)
    assert "RETIRED" in body
    assert "8787" in body
    assert "agent.html" not in body
    assert "RETIRED" in RETIRED_HTML
