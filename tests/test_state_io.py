"""Locking/atomicity tests for core.spine.state_io (tmp_path only)."""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

from core.spine.state_io import (
    append_jsonl,
    read_json,
    rmw,
    state_lock,
    write_json,
)


def test_write_read_round_trip(tmp_path):
    p = tmp_path / "state" / "x.json"
    write_json(p, {"a": 1, "b": [1, 2], "c": "τ"})
    assert read_json(p, None) == {"a": 1, "b": [1, 2], "c": "τ"}


def test_read_json_default_on_missing(tmp_path):
    assert read_json(tmp_path / "nope.json", {"pending": []}) == {"pending": []}


def test_read_json_default_on_corrupt(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert read_json(p, 42) == 42


def test_rmw_applies_mutator_and_persists(tmp_path):
    p = tmp_path / "counter.json"
    for _ in range(50):
        out = rmw(p, lambda v: {"n": v.get("n", 0) + 1}, {"n": 0})
    assert out["n"] == 50
    assert read_json(p, {})["n"] == 50


def test_rmw_concurrent_no_lost_updates(tmp_path):
    p = tmp_path / "counter.json"

    def worker():
        for _ in range(25):
            rmw(p, lambda v: {"n": v.get("n", 0) + 1}, {"n": 0})

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert read_json(p, {})["n"] == 200


def test_append_jsonl_two_records(tmp_path):
    p = tmp_path / "h.jsonl"
    append_jsonl(p, {"a": 1})
    append_jsonl(p, {"b": 2})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}


def test_stale_lock_recovered(tmp_path):
    lock = tmp_path / "x.json.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999999", encoding="utf-8")
    old = time.time() - 3600
    os.utime(lock, (old, old))
    # Lock is stale (mtime older than the timeout): acquisition must succeed.
    with state_lock(lock, timeout=0.5):
        pass
    assert not lock.exists()


def test_lock_timeout_raises(tmp_path):
    lock = tmp_path / "x.json.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()), encoding="utf-8")
    stop = threading.Event()

    def keep_fresh():
        # A live holder keeps the lock mtime young, so the waiter can never
        # mistake it for a stale lock and steal it — the timeout must fire.
        while not stop.is_set():
            try:
                os.utime(lock, None)
            except OSError:
                break
            time.sleep(0.05)

    t = threading.Thread(target=keep_fresh)
    t.start()
    try:
        with pytest.raises(TimeoutError, match="state lock timeout"):
            with state_lock(lock, timeout=0.4):
                pass  # pragma: no cover - never reached
    finally:
        stop.set()
        t.join()
        lock.unlink(missing_ok=True)


def test_write_json_leaves_no_tmp_residue(tmp_path):
    p = tmp_path / "x.json"
    write_json(p, {"a": 1})
    leftovers = [f.name for f in tmp_path.iterdir() if ".tmp." in f.name]
    assert leftovers == []
    assert p.exists()
