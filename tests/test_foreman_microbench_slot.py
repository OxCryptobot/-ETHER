"""Foreman microbench steady slot + whats_next signals."""
from __future__ import annotations


def test_steady_has_microbench_slot():
    from scripts.foreman import STEADY_TEMPLATES

    prefixes = [t["id_prefix"] for t in STEADY_TEMPLATES]
    assert "ss_microbench" in prefixes
    slot = next(t for t in STEADY_TEMPLATES if t["id_prefix"] == "ss_microbench")
    assert slot.get("class") == "measure"
    assert slot.get("continue_on_fail") is True
    argv = slot["steps"][0]["argv"]
    assert "core.microbench_schedule" in argv


def test_whats_next_signals():
    from scripts.write_whats_next import main
    import json
    from pathlib import Path

    assert main() == 0
    data = json.loads(
        (Path(__file__).resolve().parents[1] / "artifacts" / "whats_next.json").read_text(
            encoding="utf-8"
        )
    )
    assert "signals" in data
    blocked = " ".join(data.get("blocked") or [])
    assert "dual_dashboard" not in blocked
    resolved = " ".join(data.get("resolved") or [])
    assert "host-first" in resolved.lower() or "dual_dashboard" in resolved.lower()
