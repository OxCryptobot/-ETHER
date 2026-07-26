"""Batch queue unit tests (no pipeline / no network)."""

from __future__ import annotations

from pathlib import Path

import core.batch_queue as bq


def test_enqueue_and_status(tmp_path, monkeypatch):
    qpath = tmp_path / "batch_queue.json"
    monkeypatch.setattr(bq, "QUEUE_PATH", qpath)
    monkeypatch.setattr(bq, "HIST_PATH", tmp_path / "history.jsonl")

    item = bq.enqueue(kind="pipeline", title="t1", objective="print(1)", priority=5)
    assert item["id"] == 1
    assert item["title"] == "t1"

    st = bq.status()
    assert st["pending"] == 1
    assert st["next"] == "t1"

    item2 = bq.enqueue(kind="pipeline", title="t0", objective="print(0)", priority=1)
    assert item2["id"] == 2
    data = bq.load_queue()
    # priority 1 should sort first
    assert data["pending"][0]["title"] == "t0"


def test_seed_smoke(tmp_path, monkeypatch):
    qpath = tmp_path / "batch_queue.json"
    monkeypatch.setattr(bq, "QUEUE_PATH", qpath)
    monkeypatch.setattr(bq, "HIST_PATH", tmp_path / "history.jsonl")

    out = bq.seed_smoke()
    assert out["seeded"] >= 3
    st = bq.status()
    assert st["pending"] >= 3

    # second seed without force does nothing
    out2 = bq.seed_smoke()
    assert out2["seeded"] == 0
