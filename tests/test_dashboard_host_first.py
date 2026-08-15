"""Host-first Control Matrix — moonshot panels and collector contract."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_moonshot_collector_returns_15_tiles():
    from dashboard.collector_moonshots import collect_moonshots

    data = collect_moonshots()
    assert "tiles" in data
    tiles = data["tiles"]
    assert len(tiles) == 15, f"expected 15 moonshot tiles, got {len(tiles)}"
    ids = {t["id"] for t in tiles}
    for required in (
        "smoothness",
        "honest_kpi",
        "latency_slo",
        "queue_gov",
        "soft_launch",
        "train_wheels",
        "microbench",
        "measure_tick",
    ):
        assert required in ids, f"missing tile {required}"
    assert data.get("note")
    assert "legacy" not in (data.get("note") or "").lower() or "no legacy" in (
        data.get("note") or ""
    ).lower()


def test_host_agent_collector_includes_moonshots():
    from dashboard.collector_host_agent import collect_host_agent

    data = collect_host_agent()
    assert data.get("truth") == "host_agent"
    assert "moonshots" in data
    assert "queue" in data
    assert "status" in data
    ms = data["moonshots"]
    assert isinstance(ms, dict)
    # tiles may be empty list only on hard error; prefer presence
    if "error" not in ms:
        assert len(ms.get("tiles") or []) == 15


def test_app_routes_primary_is_agent(tmp_path=None):
    """/ and /agent both resolve to agent.html; /legacy is archive."""
    from dashboard import app as dash_app

    routes = {getattr(r, "path", None) for r in dash_app.app.routes}
    assert "/" in routes
    assert "/agent" in routes
    assert "/api/host-agent" in routes
    assert "/api/moonshots" in routes
    assert "/legacy" in routes


def test_no_guardian_as_primary_in_moonshots():
    from dashboard.collector_moonshots import collect_moonshots

    data = collect_moonshots()
    blob = json.dumps(data).lower()
    assert "guardian frozen" not in blob
    assert "smoke is_even" not in blob
