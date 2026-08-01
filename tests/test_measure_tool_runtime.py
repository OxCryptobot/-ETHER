"""Harness smoke — offline scripted only."""
from scripts.measure_tool_runtime import measure_one


def test_measure_greeter_scripted():
    r = measure_one("greeter", live=False, max_steps=6, timeout_s=60)
    assert r["ok"] is True
    assert r["score"] == 1.0
    assert r["mode"] == "scripted"


def test_measure_wallet_scripted():
    r = measure_one("wallet", live=False, max_steps=6, timeout_s=60)
    assert r["ok"] is True
    assert r["score"] == 1.0
