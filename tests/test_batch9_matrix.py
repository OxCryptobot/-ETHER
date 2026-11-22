"""Batch 9 item 6: Matrix read-only learning view; dashboard write routes refused by default."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _art(tmp_path: Path) -> Path:
    art = tmp_path / "artifacts"
    art.mkdir()
    now = datetime.now(timezone.utc).isoformat()
    (art / "learning_summary.json").write_text(json.dumps({
        "schema": 2, "generated": now,
        "metrics": {"attempts": 40, "kept": 6, "kept_per_attempt": 0.15, "revert_rate": 0.7, "dup_share": 0.2,
                    "kept_per_gpu_hour": 3.1, "filler_rate": 0.0, "regressions_caught": 4},
        "arms": {"fix_test": {"default": {"pulls": 30, "passes": 5, "pass_rate": 0.167},
                              "repair_heavy": {"pulls": 10, "passes": 1, "pass_rate": 0.1}}},
        "bandit": {"algo": "thompson"}, "real_queue": {"open": 12, "done": 6, "dropped": {}},
        "recent": [{"goal": "g", "reply": "SECRET PROMPT TEXT"}],
    }), encoding="utf-8")
    (art / "supervisor.json").write_text(json.dumps({"ts": now, "health": "failing", "pull_failures": 5,
                                                     "health_worst": "pull: git pull failed (rc 128)"}), encoding="utf-8")
    (art / "host_main.json").write_text(json.dumps({"ts": now, "health": "degraded"}), encoding="utf-8")
    (art / "pull_diverged.json").write_text(json.dumps({"fix": "git reset --keep origin/main"}), encoding="utf-8")
    return art


def test_snapshot_shows_learning_health_and_capabilities(tmp_path, monkeypatch):
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    art = _art(tmp_path)
    before = {p.name: p.read_text(encoding="utf-8") for p in art.iterdir()}
    from scripts.unison import snapshot

    row = snapshot()
    lv = row["learning"]
    assert lv["present"] and lv["kept_per_attempt"] == 0.15 and lv["dup_share"] == 0.2 and lv["revert_rate"] == 0.7
    assert lv["arms"]["fix_test"]["default"] == {"pulls": 30, "pass_rate": 0.167}
    assert lv["top_arm_share"] == 0.75 and lv["bandit_algo"] == "thompson" and lv["stale"] is False
    hv = row["health"]
    assert hv["health"] == "failing" and hv["pull_failures"] == 5 and "reset --keep" in hv["pull_fix"]
    assert row["skills"] == ["search", "read"]
    assert row["capabilities"]["gate_sandbox"] is True and row["capabilities"]["planted_goals"] is False
    assert "SECRET PROMPT TEXT" not in json.dumps(row)
    assert {p.name: p.read_text(encoding="utf-8") for p in art.iterdir()} == before  # read-only
    assert row["mutates"] is False


def test_snapshot_without_learning_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    (tmp_path / "artifacts").mkdir()
    from scripts.unison import snapshot

    row = snapshot()
    assert row["learning"] == {"present": False} and row["health"]["health"] == "unknown"


def test_host_main_refreshes_the_read_model_on_the_writer():
    src = Path("scripts/host_main.py").read_text(encoding="utf-8")
    nt_branch = src.split('if os.name == "nt":', 1)[1].split("    else:\n        try:\n            from scripts.ether_evolve", 1)[0]
    assert "publish_observer()" in nt_branch


def test_dashboard_refuses_writes_by_default(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from dashboard.app import app

    monkeypatch.delenv("ETHER_DASHBOARD_WRITE", raising=False)
    client = TestClient(app)
    for path in ("/api/promote", "/api/reconcile-tools", "/api/test", "/api/chat", "/api/chat/clear",
                 "/api/health-check", "/api/speech", "/api/upload"):
        r = client.post(path, json={})
        assert r.status_code == 403 and r.json()["error"] == "read_only", path
    assert client.get("/api/unison").status_code == 200


def test_dashboard_write_needs_flag_token_and_local_origin(monkeypatch):
    from dashboard.app import write_allowed

    tok = "t" * 20
    hdr = {"x-ether-token": tok, "host": "127.0.0.1:8787"}
    assert write_allowed("GET", {}) is True
    assert write_allowed("POST", hdr) is False  # flag off
    monkeypatch.setenv("ETHER_DASHBOARD_WRITE", "1")
    assert write_allowed("POST", hdr) is False  # no token configured
    monkeypatch.setenv("ETHER_DASHBOARD_TOKEN", tok)
    assert write_allowed("POST", hdr) is True
    assert write_allowed("POST", {**hdr, "x-ether-token": "wrong"}) is False
    assert write_allowed("POST", {**hdr, "origin": "https://evil.example"}) is False
    assert write_allowed("POST", {**hdr, "host": "evil.example"}) is False  # DNS rebinding
    monkeypatch.setenv("ETHER_DASHBOARD_TOKEN", "short")
    assert write_allowed("POST", {**hdr, "x-ether-token": "short"}) is False
