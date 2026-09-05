"""FAST: live_unaided seed-hard path is importable. --live is host work."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MOD = Path(__file__).resolve().parents[1] / "scripts" / "live_unaided.py"
_SPEC = importlib.util.spec_from_file_location("ether_live_unaided", _MOD)
assert _SPEC and _SPEC.loader
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


def test_seed_is_hard_lru() -> None:
    out = mod.seed_is_hard("lru")
    assert out["name"] == "lru"
    assert "workspace" in out
    assert "ok" in out
