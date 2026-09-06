"""Bounded walk: parseable BUG:should steps apply; does not call Pipeline.run."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

from core.loop.walk_fixture import walk_bounded


def test_walk_bounded_lru_does_not_hang() -> None:
    out = walk_bounded("lru", timeout=45)
    assert out["ok"] is True
    assert out["gate_count"] is False
    assert out["policy"] == "craft_helper"
    assert out["n_applied"] >= 1


def test_live_unaided_live_uses_walk_bounded() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "live_unaided.py"
    spec = importlib.util.spec_from_file_location("ether_live_unaided2", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = inspect.getsource(mod.run_live)
    assert "walk_bounded" in src
    assert "Pipeline" not in src
