"""Live fixture denylist contracts."""
from __future__ import annotations


def test_publish_runs():
    from core.live_fixture_policy import publish

    p = publish()
    assert "denied" in p
    assert isinstance(p["denied"], list)
    assert p.get("path")


def test_should_skip_empty_fixture():
    from core.live_fixture_policy import should_skip_live

    d = should_skip_live(fixture="totally_unknown_fixture_xyz")
    assert d["skip"] is False


def test_filter_fast_first_keeps_fast():
    from pathlib import Path
    import tempfile
    import json
    from core.host_schedule import filter_fast_first

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fast = root / "f.json"
        live = root / "l.json"
        fast.write_text(json.dumps({"id": "a", "class": "fast"}), encoding="utf-8")
        live.write_text(json.dumps({"id": "b", "class": "live"}), encoding="utf-8")
        out = filter_fast_first([fast, live])
        assert fast in out
        assert live not in out


def test_filter_live_denylist_noop_on_fast():
    from pathlib import Path
    import tempfile
    import json
    from core.host_schedule import filter_live_denylist

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fast = root / "f.json"
        fast.write_text(json.dumps({"id": "a", "class": "fast"}), encoding="utf-8")
        out = filter_live_denylist([fast])
        assert out == [fast]
